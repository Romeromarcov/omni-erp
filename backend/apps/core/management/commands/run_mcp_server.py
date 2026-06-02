"""
Management command para arrancar el Omni MCP Server.

Uso:
  python manage.py run_mcp_server           → stdio (Claude Desktop, agentes CLI)
  python manage.py run_mcp_server --sse     → SSE/HTTP (agentes web, integraciones)
  python manage.py run_mcp_server --port 8001

El servidor stdio es el modo estándar para MCP: lee requests de stdin
y escribe responses en stdout. Compatible con Claude Desktop y otros clientes MCP.

El servidor SSE expone un endpoint HTTP para clientes que no soportan stdio.
"""

import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Arranca el servidor MCP de Omni (Model Context Protocol)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sse",
            action="store_true",
            default=False,
            help="Usar transporte SSE/HTTP en lugar de stdio (default: stdio)",
        )
        parser.add_argument(
            "--host",
            type=str,
            default="0.0.0.0",  # nosec B104
            help="Host para SSE (default: 0.0.0.0)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8001,
            help="Puerto para SSE (default: 8001)",
        )

    def handle(self, *args, **options):
        try:
            from apps.core.mcp_server import MCP_AVAILABLE, mcp  # noqa: PLC0415
        except ImportError as exc:
            self.stderr.write(self.style.ERROR(f"No se pudo importar mcp_server: {exc}"))
            sys.exit(1)

        if not MCP_AVAILABLE or mcp is None:
            self.stderr.write(
                self.style.ERROR(
                    "El SDK de MCP no está disponible. "
                    "Instala el paquete: pip install mcp"
                )
            )
            sys.exit(1)

        transport = "sse" if options["sse"] else "stdio"

        if transport == "sse":
            self.stdout.write(
                self.style.SUCCESS(
                    f"Iniciando Omni MCP Server en modo SSE "
                    f"→ http://{options['host']}:{options['port']}/sse"
                )
            )
            mcp.run(
                transport="sse",
                host=options["host"],
                port=options["port"],
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Iniciando Omni MCP Server en modo stdio...")
            )
            mcp.run(transport="stdio")
