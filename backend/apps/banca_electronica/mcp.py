"""
apps/banca_electronica/mcp.py — Herramientas MCP para Banca Electrónica VE (Ola B5).

Herramientas expuestas:
  banca_validar_referencia — verifica referencias bancarias duplicadas en el tenant
  banca_listar_lotes_pago  — lista lotes de pago bancario de una empresa
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("omni.mcp.banca_electronica")

_SCOPE = "banca_electronica"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def banca_validar_referencia(
    capability_token: str,
    empresa_id: str,
    cuenta_bancaria_id: str,
    referencia: str,
) -> Any:
    """
    Detecta si una referencia bancaria ya fue utilizada en pagos, extractos o lotes del tenant.

    Scope requerido: ``banca_electronica:read``
    """
    from apps.banca_electronica.services import validar_referencia_bancaria  # noqa: PLC0415
    from apps.finanzas.models import CuentaBancariaEmpresa  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        uuid.UUID(str(empresa_id))
        cuenta = None
        if cuenta_bancaria_id:
            cuenta_uuid = uuid.UUID(str(cuenta_bancaria_id))
            cuenta = CuentaBancariaEmpresa.objects.filter(
                pk=cuenta_uuid,
                id_empresa_id=empresa_id,
            ).first()
            if cuenta is None:
                return {"error": f"Cuenta bancaria {cuenta_bancaria_id} no encontrada en la empresa {empresa_id}."}

        resultado = validar_referencia_bancaria(
            empresa=empresa_id,
            cuenta_bancaria=cuenta,
            referencia=referencia,
        )
        logger.info(
            "banca_validar_referencia | actor=%s | tenant=%s | duplicada=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            resultado["duplicada"],
        )
        return resultado


def banca_listar_lotes_pago(
    capability_token: str,
    empresa_id: str,
    tipo_lote: str = "",
    estado: str = "",
    limit: int = 25,
) -> Any:
    """
    Lista lotes de pago bancario VE (proveedores / nómina) para una empresa.

    Scope requerido: ``banca_electronica:read``
    """
    from apps.banca_electronica.models import LotePagoBancario  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        uuid.UUID(str(empresa_id))
        limit_norm = max(1, min(int(limit), 200))
        qs = LotePagoBancario.objects.select_related("id_cuenta_bancaria").filter(
            id_empresa_id=empresa_id,
        )
        if tipo_lote:
            qs = qs.filter(tipo_lote=tipo_lote.strip())
        if estado:
            qs = qs.filter(estado=estado.strip())

        lotes = list(qs.order_by("-fecha_valor", "-fecha_creacion")[:limit_norm])
        logger.info(
            "banca_listar_lotes_pago | actor=%s | tenant=%s | total=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(lotes),
        )
        return [
            {
                "id_lote_pago": str(lote.pk),
                "referencia_lote": lote.referencia_lote,
                "tipo_lote": lote.tipo_lote,
                "formato_banco": lote.formato_banco,
                "fecha_valor": lote.fecha_valor.isoformat(),
                "estado": lote.estado,
                "total_registros": lote.total_registros,
                "monto_total": str(lote.monto_total),
                "nombre_archivo": lote.nombre_archivo,
                "sha256_archivo": lote.sha256_archivo,
                "id_cuenta_bancaria": str(lote.id_cuenta_bancaria_id),
                "cuenta_banco": lote.id_cuenta_bancaria.nombre_banco,
            }
            for lote in lotes
        ]


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": banca_validar_referencia,
        "name": "banca_validar_referencia",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": banca_listar_lotes_pago,
        "name": "banca_listar_lotes_pago",
        "scope": f"{_SCOPE}:read",
    },
]
