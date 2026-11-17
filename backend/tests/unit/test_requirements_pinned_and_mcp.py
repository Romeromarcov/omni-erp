"""
Validación de pines exactos en requirements.txt y activación de FastMCP (Plan 06 §1.3).

Garantiza que:
1. Toda dependencia activa en ``backend/requirements.txt`` usa pin exacto ``==``
   (sin rangos abiertos ``>=``, ``<=``, ``~=``, ``!=``, comodines ``*`` ni paquetes
   sin versión).
2. ``apps.core.mcp_server.MCP_AVAILABLE`` es ``True`` (``mcp==1.30.0`` expone
   ``mcp.server.fastmcp.FastMCP``) y las herramientas MCP base quedan registradas.
"""

import asyncio
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND_DIR = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = BACKEND_DIR / "requirements.txt"

EXACT_PIN_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9.,_-]+\])?==[A-Za-z0-9.+_-]+$"
)
FORBIDDEN_SPEC_TOKENS = (">=", "<=", "~=", "!=", "===", ">", "<", "*")

BASE_MCP_TOOLS = {
    "omni_ping",
    "omni_get_empresas",
    "omni_get_clientes",
    "omni_get_saldo_cliente",
    "omni_get_cxc_aging",
    "omni_get_stock_producto",
    "omni_get_ventas_resumen",
    "omni_buscar_contacto",
    "omni_crear_pedido",
    "omni_get_pedidos",
    "omni_registrar_movimiento_inventario",
    "omni_get_correlativo_fiscal",
    "omni_buscar_cliente",
    "omni_cxc_get_cartera_vencida",
    "omni_cxc_get_aging_summary",
    "omni_cxc_get_tasa_cambio_hoy",
    "omni_cxc_get_acuerdos_vigentes",
}


def _active_requirement_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        cleaned = re.sub(r"(^|\s)#.*$", "", raw_line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def test_requirements_txt_uses_exact_pins():
    """H7 / Plan 06 §1.3: ninguna dependencia en requirements.txt debe quedar sin pin ==."""
    lines = _active_requirement_lines(REQUIREMENTS_PATH)
    assert lines, "requirements.txt no puede estar vacío"

    invalid: list[str] = []
    packages: dict[str, str] = {}

    for line in lines:
        spec = line.split(";", 1)[0].strip()
        if any(tok in spec for tok in FORBIDDEN_SPEC_TOKENS) or not EXACT_PIN_RE.match(
            spec
        ):
            invalid.append(line)
            continue
        name, version = spec.split("==", 1)
        normalized_name = name.split("[", 1)[0].lower().replace("_", "-")
        packages[normalized_name] = version

    assert (
        not invalid
    ), f"Dependencias sin pin exacto '==' en requirements.txt: {invalid}"
    for expected in ("mcp", "confluent-kafka", "django-ratelimit", "anthropic"):
        assert (
            expected in packages
        ), f"Falta dependencia requerida en requirements.txt: {expected}"


def test_mcp_available_and_base_tools_registered():
    """mcp==1.30.0 restaura FastMCP (MCP_AVAILABLE=True) y registra las 17 tools base."""
    from apps.core import mcp_server

    assert mcp_server.MCP_AVAILABLE is True
    assert mcp_server.mcp is not None

    registered = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
    missing = BASE_MCP_TOOLS - registered
    assert (
        not missing
    ), f"Faltan tools MCP base registradas en FastMCP: {sorted(missing)}"
