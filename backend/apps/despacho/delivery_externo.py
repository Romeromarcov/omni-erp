"""Puerto y adaptadores para integraciones con apps/plataformas de Delivery Externo (Plan 09 Fase 6.3).

Expone ``ProveedorDeliveryExterno`` y adaptadores concretos:
- ``SimuladoDeliveryAdapter`` (determinista offline para pruebas/staging).
- ``UberDirectAdapter``, ``RideryAdapter`` y ``YummyAdapter`` (HTTP opt-in con transporte inyectable).
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class DeliveryExternoError(Exception):
    """Error al cotizar, solicitar, consultar o cancelar con proveedor externo."""


def _safe_int(val: Any, *, default: int, campo: str) -> int:
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (TypeError, ValueError) as exc:
        raise DeliveryExternoError(f"Respuesta inválida del proveedor externo en '{campo}'.") from exc


class ProveedorDeliveryExterno(ABC):
    codigo: str = ""

    @abstractmethod
    def cotizar(
        self,
        *,
        origen_lat: Decimal,
        origen_lng: Decimal,
        destino_lat: Decimal,
        destino_lng: Decimal,
        peso_kg: Decimal,
    ) -> dict[str, Any]:
        """Retorna cotización estimada (``tarifa_usd``, ``eta_minutos``, ``moneda``)."""

    @abstractmethod
    def solicitar_entrega(
        self,
        *,
        referencia_ruta: str,
        origen_lat: Decimal,
        origen_lng: Decimal,
        destino_lat: Decimal,
        destino_lng: Decimal,
        direccion_destino: str,
        peso_kg: Decimal,
    ) -> dict[str, Any]:
        """Solicita unidad externa y retorna ``referencia_externa``, ``tracking_url``, ``tarifa_usd``."""

    @abstractmethod
    def consultar_tracking(self, *, referencia_externa: str) -> dict[str, Any]:
        """Consulta estado y ubicación en vivo de una orden externa."""

    @abstractmethod
    def cancelar_entrega(self, *, referencia_externa: str, motivo: str = "") -> dict[str, Any]:
        """Cancela una solicitud de entrega externa."""


class SimuladoDeliveryAdapter(ProveedorDeliveryExterno):
    """Adaptador determinista local para desarrollo, pruebas y staging sin red."""

    codigo = "SIMULADO"

    def __init__(self, codigo: str = "SIMULADO", tarifa_km_usd: Decimal = Decimal("0.8500")) -> None:
        self.codigo = codigo
        self._tarifa_km = tarifa_km_usd

    def cotizar(
        self,
        *,
        origen_lat: Decimal,
        origen_lng: Decimal,
        destino_lat: Decimal,
        destino_lng: Decimal,
        peso_kg: Decimal,
    ) -> dict[str, Any]:
        from .services_vrp import distancia_haversine_km

        dist = distancia_haversine_km(origen_lat, origen_lng, destino_lat, destino_lng)
        recargo_peso = (peso_kg * Decimal("0.05")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        tarifa = (Decimal("2.5000") + (dist * self._tarifa_km) + recargo_peso).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        eta_min = max(12, int((dist * Decimal("3")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) + 10)
        return {
            "proveedor": self.codigo,
            "distancia_km": str(dist),
            "tarifa_usd": str(tarifa),
            "eta_minutos": eta_min,
            "moneda": "USD",
        }

    def solicitar_entrega(
        self,
        *,
        referencia_ruta: str,
        origen_lat: Decimal,
        origen_lng: Decimal,
        destino_lat: Decimal,
        destino_lng: Decimal,
        direccion_destino: str,
        peso_kg: Decimal,
    ) -> dict[str, Any]:
        cot = self.cotizar(
            origen_lat=origen_lat,
            origen_lng=origen_lng,
            destino_lat=destino_lat,
            destino_lng=destino_lng,
            peso_kg=peso_kg,
        )
        digest = (
            hashlib.sha256(f"{self.codigo}:{referencia_ruta}:{direccion_destino}".encode()).hexdigest()[:10].upper()
        )
        ref = f"{self.codigo}-{digest}"
        return {
            "proveedor": self.codigo,
            "referencia_externa": ref,
            "tracking_url": f"https://tracking.omni-erp.local/{self.codigo.lower()}/{ref}",
            "tarifa_usd": cot["tarifa_usd"],
            "eta_minutos": cot["eta_minutos"],
            "estado": "ASIGNADO",
        }

    def consultar_tracking(self, *, referencia_externa: str) -> dict[str, Any]:
        if not (referencia_externa or "").strip():
            raise DeliveryExternoError("referencia_externa requerida para consultar tracking.")
        return {
            "proveedor": self.codigo,
            "referencia_externa": referencia_externa,
            "estado": "EN_CAMINO",
            "latitud_repartidor": "10.491016",
            "longitud_repartidor": "-66.879190",
            "eta_minutos": 14,
        }

    def cancelar_entrega(self, *, referencia_externa: str, motivo: str = "") -> dict[str, Any]:
        if not (referencia_externa or "").strip():
            raise DeliveryExternoError("referencia_externa requerida para cancelar.")
        return {
            "proveedor": self.codigo,
            "referencia_externa": referencia_externa,
            "estado": "CANCELADO",
            "motivo": motivo,
        }


class _BaseHttpDeliveryAdapter(ProveedorDeliveryExterno):
    """Cliente HTTP base seguro para proveedores externos reales (HTTPS obligatorio)."""

    def __init__(
        self,
        *,
        codigo: str,
        base_url: str,
        api_token: str,
        transport: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.codigo = codigo
        self._base_url = (base_url or "").strip().rstrip("/")
        self._api_token = (api_token or "").strip()
        self._transport = transport

    def _call(self, method: str, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._transport is not None:
            return self._transport(method=method, endpoint=endpoint, payload=payload or {}, provider=self.codigo)
        if not self._base_url or not self._api_token:
            raise DeliveryExternoError(
                f"Credenciales/URL no configuradas para proveedor '{self.codigo}' (base_url/api_token)."
            )
        if not self._base_url.startswith("https://"):
            raise DeliveryExternoError(f"La URL del proveedor '{self.codigo}' debe usar HTTPS.")
        url = f"{self._base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {self._api_token}", "Content-Type": "application/json"}
        try:
            resp = requests.request(method, url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            return dict(resp.json())
        except Exception as exc:
            logger.warning("delivery_externo error | provider=%s | err=%s", self.codigo, type(exc).__name__)
            raise DeliveryExternoError(f"Error de comunicación con el proveedor externo '{self.codigo}'.") from exc

    def cotizar(
        self,
        *,
        origen_lat: Decimal,
        origen_lng: Decimal,
        destino_lat: Decimal,
        destino_lng: Decimal,
        peso_kg: Decimal,
    ) -> dict[str, Any]:
        data = self._call(
            "POST",
            "/quotes",
            {
                "pickup": {"lat": str(origen_lat), "lng": str(origen_lng)},
                "dropoff": {"lat": str(destino_lat), "lng": str(destino_lng)},
                "weight_kg": str(peso_kg),
            },
        )
        return {
            "proveedor": self.codigo,
            "tarifa_usd": str(data.get("tarifa_usd", data.get("fee", "0.0000"))),
            "eta_minutos": _safe_int(data.get("eta_minutos", data.get("duration")), default=20, campo="eta_minutos"),
            "moneda": str(data.get("moneda", "USD")),
        }

    def solicitar_entrega(
        self,
        *,
        referencia_ruta: str,
        origen_lat: Decimal,
        origen_lng: Decimal,
        destino_lat: Decimal,
        destino_lng: Decimal,
        direccion_destino: str,
        peso_kg: Decimal,
    ) -> dict[str, Any]:
        data = self._call(
            "POST",
            "/deliveries",
            {
                "external_id": referencia_ruta,
                "pickup": {"lat": str(origen_lat), "lng": str(origen_lng)},
                "dropoff": {"lat": str(destino_lat), "lng": str(destino_lng), "address": direccion_destino},
                "weight_kg": str(peso_kg),
            },
        )
        ref = str(data.get("referencia_externa") or "").strip()
        if not ref:
            raise DeliveryExternoError("Respuesta inválida del proveedor externo: falta 'referencia_externa'.")
        return {
            "proveedor": self.codigo,
            "referencia_externa": ref,
            "tracking_url": str(data.get("tracking_url", "")),
            "tarifa_usd": str(data.get("tarifa_usd", "0.0000")),
            "eta_minutos": _safe_int(data.get("eta_minutos"), default=20, campo="eta_minutos"),
            "estado": str(data.get("estado", "ASIGNADO")),
        }

    def consultar_tracking(self, *, referencia_externa: str) -> dict[str, Any]:
        ref_q = quote(str(referencia_externa), safe="")
        data = self._call("GET", f"/deliveries/{ref_q}")
        return {
            "proveedor": self.codigo,
            "referencia_externa": referencia_externa,
            "estado": str(data.get("estado", "EN_CAMINO")),
            "latitud_repartidor": str(data.get("latitud_repartidor", "")),
            "longitud_repartidor": str(data.get("longitud_repartidor", "")),
            "eta_minutos": _safe_int(data.get("eta_minutos"), default=15, campo="eta_minutos"),
        }

    def cancelar_entrega(self, *, referencia_externa: str, motivo: str = "") -> dict[str, Any]:
        ref_q = quote(str(referencia_externa), safe="")
        data = self._call("POST", f"/deliveries/{ref_q}/cancel", {"motivo": motivo})
        return {
            "proveedor": self.codigo,
            "referencia_externa": referencia_externa,
            "estado": str(data.get("estado", "CANCELADO")),
            "motivo": motivo,
        }


class UberDirectAdapter(_BaseHttpDeliveryAdapter):
    def __init__(self, *, base_url: str = "", api_token: str = "", transport=None) -> None:
        super().__init__(codigo="UBER_DIRECT", base_url=base_url, api_token=api_token, transport=transport)


class RideryAdapter(_BaseHttpDeliveryAdapter):
    def __init__(self, *, base_url: str = "", api_token: str = "", transport=None) -> None:
        super().__init__(codigo="RIDERY", base_url=base_url, api_token=api_token, transport=transport)


class YummyAdapter(_BaseHttpDeliveryAdapter):
    def __init__(self, *, base_url: str = "", api_token: str = "", transport=None) -> None:
        super().__init__(codigo="YUMMY", base_url=base_url, api_token=api_token, transport=transport)


def obtener_proveedor_delivery(
    codigo: str,
    *,
    config: dict[str, str] | None = None,
    transport: Callable[..., dict[str, Any]] | None = None,
) -> ProveedorDeliveryExterno:
    """Fábrica de adaptadores ``ProveedorDeliveryExterno``."""
    cod = (codigo or "").strip().upper()
    cfg = config or {}
    if cod == "SIMULADO":
        return SimuladoDeliveryAdapter(codigo="SIMULADO")
    if cod == "UBER_DIRECT":
        if transport is None and not cfg.get("base_url"):
            return SimuladoDeliveryAdapter(codigo="UBER_DIRECT", tarifa_km_usd=Decimal("1.1000"))
        return UberDirectAdapter(
            base_url=cfg.get("base_url", ""), api_token=cfg.get("api_token", ""), transport=transport
        )
    if cod == "RIDERY":
        if transport is None and not cfg.get("base_url"):
            return SimuladoDeliveryAdapter(codigo="RIDERY", tarifa_km_usd=Decimal("0.7500"))
        return RideryAdapter(base_url=cfg.get("base_url", ""), api_token=cfg.get("api_token", ""), transport=transport)
    if cod == "YUMMY":
        if transport is None and not cfg.get("base_url"):
            return SimuladoDeliveryAdapter(codigo="YUMMY", tarifa_km_usd=Decimal("0.8000"))
        return YummyAdapter(base_url=cfg.get("base_url", ""), api_token=cfg.get("api_token", ""), transport=transport)
    raise DeliveryExternoError(f"Proveedor de delivery externo no soportado: '{codigo}'.")
