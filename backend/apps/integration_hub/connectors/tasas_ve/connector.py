"""
TasasVeConnector — Conector para tasas de cambio venezolanas.

No requiere ConectorInstancia (APIs públicas).
Cascade BCV: dolarapi → exchangedynamic → bcv_scrape.
Binance P2P: promedio 5 BUY + 5 SELL.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from apps.integration_hub.connectors.base import BaseConnector, TestConnectionResult

logger = logging.getLogger(__name__)


class TasasVeConnector(BaseConnector):
    PROVIDER_CODE = "tasas_ve"
    PROVIDER_NAME = "Tasas Venezuela (BCV + Binance P2P)"
    SUPPORTED_ENTITIES = ["tasa_bcv", "tasa_binance_p2p"]

    def __init__(self, instancia=None):
        # No requiere ConectorInstancia — APIs públicas
        self.instancia = instancia
        self._config = {}
        self.logger = logging.getLogger(f"{__name__}.TasasVeConnector")

    def test_connection(self) -> TestConnectionResult:
        tasa = self.pull_tasa_bcv()
        if tasa is not None:
            return TestConnectionResult(
                success=True,
                message=f"BCV conectado. Tasa: {tasa}",
            )
        return TestConnectionResult(
            success=False,
            message="No se pudo obtener tasa BCV (todas las fuentes fallaron)",
        )

    def get_version_info(self) -> dict:
        return {"provider": self.PROVIDER_CODE, "sources": ["dolarapi", "exchangedynamic", "bcv_scrape"]}

    def pull_tasa_bcv(self) -> Decimal | None:
        """
        Cascade de 3 fuentes BCV:
        1. dolarapi.com
        2. exchangedynamic.com
        3. bcv.org.ve (scraping con SSL workaround)
        """
        from .sources import dolarapi, exchangedynamic, bcv_scrape

        for nombre, modulo in [
            ("dolarapi", dolarapi),
            ("exchangedynamic", exchangedynamic),
            ("bcv_scrape", bcv_scrape),
        ]:
            tasa = modulo.fetch_tasa_bcv()
            if tasa is not None:
                self.logger.info("Tasa BCV obtenida via %s: %s", nombre, tasa)
                return tasa
            self.logger.warning("Fuente %s no disponible, probando siguiente", nombre)

        self.logger.error("Todas las fuentes BCV fallaron")
        return None

    def pull_tasa_binance_p2p(self) -> Decimal | None:
        """Promedio 5 BUY + 5 SELL de Binance P2P."""
        from .sources.binance_p2p import fetch_tasa_binance_p2p
        tasa = fetch_tasa_binance_p2p()
        if tasa is not None:
            self.logger.info("Tasa Binance P2P: %s", tasa)
        return tasa
