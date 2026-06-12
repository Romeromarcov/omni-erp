"""
Tests de las tools MCP / helpers corregidos por mypy+django-stubs (PR de Fase 5).

Cubren las rutas que estaban SIN test y donde el tipado destapó bugs reales de
nombres de campo (FieldError/AttributeError en runtime):
  - core.mcp_server.omni_get_empresas        (Empresa: identificador_fiscal, no 'rif')
  - core.mcp_server.omni_get_saldo_cliente   (CuentaPorCobrar: empresa_id/cliente_id)
  - finanzas.mcp.finanzas_get_saldo_caja     (CajaFisica.empresa_id/.activa; SesionCajaFisica.saldo_inicial)
  - finanzas.utils_transferencias            (guarda de empresa no-nula)
"""

from decimal import Decimal

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _token(empresa, scopes):
    from apps.core.models import CapabilityToken

    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-test", scopes=scopes)
    return str(tok.token)


# ── core.mcp_server.omni_get_empresas ───────────────────────────────────────────


def test_omni_get_empresas_devuelve_identificador_fiscal(empresa_a):
    """Antes consultaba .values('rif') (campo inexistente) → FieldError."""
    from apps.core.mcp_server import omni_get_empresas

    empresa_a.identificador_fiscal = "J-31415926-5"
    empresa_a.save(update_fields=["identificador_fiscal"])

    resultado = omni_get_empresas(_token(empresa_a, ["core:read"]))

    assert isinstance(resultado, list)
    ids = {e["id_empresa"] for e in resultado}
    assert str(empresa_a.id_empresa) in ids


# ── core.mcp_server.omni_get_saldo_cliente ──────────────────────────────────────


def test_omni_get_saldo_cliente_calcula_saldo(empresa_a):
    """
    Antes: filtraba id_empresa=/id_cliente= (FieldError) y agregaba campos
    inexistentes saldo_pendiente/id_cxc (FieldError en cada llamada) con estados
    en mayúscula. Ahora calcula monto - abonos sobre estados reales (minúscula).
    """
    from apps.core.mcp_server import omni_get_saldo_cliente
    from apps.crm.models import Cliente
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from django.utils import timezone

    cliente = Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Cliente MCP S.A.", rif="J-27182818-2"
    )
    CuentaPorCobrar.objects.create(
        cliente=cliente,
        empresa=empresa_a,
        monto=Decimal("300.00"),
        fecha_emision=timezone.now().date(),
        fecha_vencimiento=timezone.now().date(),
        estado="pendiente",
        descripcion="CxC MCP test",
    )

    resultado = omni_get_saldo_cliente(
        _token(empresa_a, ["cxc:read"]), str(empresa_a.id_empresa), str(cliente.id_cliente)
    )

    assert resultado["total_pendiente"] == Decimal("300.00")
    assert resultado["cantidad_facturas"] == 1


# ── finanzas.mcp.finanzas_get_saldo_caja ────────────────────────────────────────


def test_finanzas_get_saldo_caja_usa_campos_correctos(empresa_a, user_a, moneda_usd):
    """Antes: get(id_empresa=), .monto_apertura, .activo → FieldError/AttributeError."""
    from apps.finanzas.mcp import finanzas_get_saldo_caja
    from apps.finanzas.models import CajaFisica, SesionCajaFisica

    caja = CajaFisica.objects.create(
        empresa=empresa_a,
        nombre="Caja MCP",
        identificador_dispositivo="dev-mcp-001",
    )
    SesionCajaFisica.objects.create(
        caja_fisica=caja,
        usuario=user_a,
        empresa=empresa_a,
        saldo_inicial=Decimal("75.00"),
    )

    resultado = finanzas_get_saldo_caja(
        _token(empresa_a, ["finanzas:read"]), str(empresa_a.id_empresa), str(caja.id_caja_fisica)
    )

    assert resultado["nombre"] == "Caja MCP"
    assert resultado["activa"] is True
    assert resultado["saldo_apertura"] == Decimal("75.00")
    assert resultado["sesion_activa"] is True


# ── finanzas.utils_transferencias — guarda de empresa ───────────────────────────


def test_transferencia_sin_empresa_lanza_valueerror(empresa_a, moneda_usd):
    """La guarda nueva exige que ambas cajas tengan empresa asignada."""
    from apps.finanzas.models import Caja
    from apps.finanzas.utils_transferencias import transferencia_entre_cajas

    origen = Caja.objects.create(
        empresa=empresa_a, nombre="Origen", tipo_caja="REGISTRADORA", moneda=moneda_usd
    )
    destino = Caja.objects.create(
        empresa=empresa_a, nombre="Destino", tipo_caja="REGISTRADORA", moneda=moneda_usd
    )

    # Simula una caja sin empresa (dato inconsistente) → debe fallar explícito.
    origen.empresa = None
    with pytest.raises(ValueError, match="empresa"):
        transferencia_entre_cajas(origen, destino, Decimal("10.00"))
