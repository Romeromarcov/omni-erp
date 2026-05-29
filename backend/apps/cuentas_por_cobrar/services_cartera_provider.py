"""
Fábrica CarteraProvider — abstrae el origen de la cartera (Mode A / Mode B).

Mode A (datasource='odoo'): Lee de Odoo vía Integration Hub.
Mode B (datasource='native'): Lee de CuentaPorCobrar nativo de Omni.

CxC nunca llama al Hub ni a CuentaPorCobrar directamente.
Siempre pasa por get_cartera_provider().
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


def _get_datasource_config(empresa) -> str:
    """
    Lee configuracion_motor.ParametroSistema para el datasource de CxC.
    Por defecto: 'native'.
    """
    from apps.configuracion_motor.models import ParametroSistema

    try:
        param = ParametroSistema.objects.get(
            id_empresa=empresa,
            codigo_parametro="cxc.datasource",
            activo=True,
        )
        return param.valor_parametro.strip().lower()
    except ParametroSistema.DoesNotExist:
        return "native"


def get_cartera_provider(empresa) -> "CarteraProvider":
    """
    Lee config del tenant y retorna el provider correcto.
    empresa: instancia de core.Empresa
    """
    datasource = _get_datasource_config(empresa)
    if datasource == "odoo":
        return OdooCarteraProvider(empresa)
    return NativeCarteraProvider(empresa)


class CarteraProvider(ABC):
    """Interfaz base para proveedores de cartera."""

    def __init__(self, empresa):
        self.empresa = empresa

    @abstractmethod
    def get_partidas(self, solo_vencidas: bool = False, fecha_desde=None) -> list:
        """Retorna lista de PartidaCartera."""

    @abstractmethod
    def get_pagos_cliente(self, cliente_id: str) -> list[dict]:
        """Retorna pagos de un cliente."""


class OdooCarteraProvider(CarteraProvider):
    """
    Mode A: usa ConectorInstancia de Odoo del tenant.
    Nunca llama a Odoo directamente — siempre vía Hub connector.
    """

    def _get_connector(self):
        from apps.integration_hub.connectors.registry import registry
        from apps.integration_hub.models import ConectorInstancia

        try:
            instancia = ConectorInstancia.objects.select_related("id_proveedor").get(
                id_empresa=self.empresa,
                id_proveedor__codigo="odoo",
                activo=True,
                estado="activo",
            )
            return registry.get_connector(instancia)
        except ConectorInstancia.DoesNotExist:
            raise RuntimeError(
                f"No hay instancia Odoo activa para empresa {self.empresa.pk}"
            )

    def get_partidas(self, solo_vencidas: bool = False, fecha_desde=None) -> list:
        from apps.cuentas_por_cobrar.services_aging import PartidaCartera

        connector = self._get_connector()
        raw_list = connector.pull_cartera_vencida(
            desde=fecha_desde,
            solo_vencidas=solo_vencidas,
        )
        return [PartidaCartera.from_hub_dict(d) for d in raw_list]

    def get_pagos_cliente(self, cliente_id: str) -> list[dict]:
        connector = self._get_connector()
        return connector.pull_pagos_cliente(cliente_id)


class NativeCarteraProvider(CarteraProvider):
    """Mode B: consulta CuentaPorCobrar nativo de Omni."""

    def get_partidas(self, solo_vencidas: bool = False, fecha_desde=None) -> list:
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar
        from apps.cuentas_por_cobrar.services_aging import PartidaCartera

        qs = CuentaPorCobrar.objects.filter(
            empresa=self.empresa,
            estado__in=["pendiente", "parcial", "vencida"],
        ).prefetch_related("abonos").select_related("cliente")

        if fecha_desde:
            qs = qs.filter(fecha_vencimiento__gte=fecha_desde)

        partidas = [PartidaCartera.from_omni(cxc) for cxc in qs]

        if solo_vencidas:
            partidas = [p for p in partidas if p.vencida]

        return partidas

    def get_pagos_cliente(self, cliente_id: str) -> list[dict]:
        from apps.cuentas_por_cobrar.models import AbonoCxC

        abonos = AbonoCxC.objects.filter(
            cuenta_por_cobrar__cliente_id=cliente_id,
            cuenta_por_cobrar__empresa=self.empresa,
        ).select_related("cuenta_por_cobrar").order_by("-fecha_abono")

        return [
            {
                "pago_id": str(a.pk),
                "fecha": str(a.fecha_abono),
                "monto": str(a.monto),
                "descripcion": a.descripcion or "",
                "cxc_ref": a.cuenta_por_cobrar.referencia_externa or str(a.cuenta_por_cobrar.pk),
            }
            for a in abonos[:50]
        ]
