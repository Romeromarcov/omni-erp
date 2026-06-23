"""
GenericRestConnector — conector genérico REST (Integration Hub, Fase 3).

Permite sumar sistemas externos que exponen una API REST/JSON **sin escribir un
conector por cada uno**: toda la lógica se configura por datos en
``ConectorInstancia.configuracion`` y la clase se conecta al sistema vía el
registry dinámico (``ConectorProveedor.clase_conector`` → esta clase).

Configuración esperada (``instancia.configuracion``)::

    {
      "base_url": "https://api.mierp.com",          # obligatorio
      "headers": {"Authorization": "Bearer ..."},   # opcional (secreto, no se loguea)
      "timeout": 30,                                 # opcional
      "verify_ssl": true,                            # opcional
      "test_endpoint": "/health",                    # opcional (para test_connection)
      "entidades": {
        "contactos": {
          "endpoint": "/clientes",
          "raiz": "data",                            # opcional: ruta a la lista anidada
          "mapa": {                                  # campo canónico → campo de la API
            "id_externo": "id",
            "nombre": "razon_social",
            "email": "correo",
            "identificador_fiscal": "rif",
            "es_cliente": "es_cliente"
          }
        },
        "productos": { "endpoint": "/productos", "mapa": {...} }
      }
    }

Solo lectura (``pull_*``); nunca modifica el sistema externo. R-CODE-8: jamás se
loguean ni se incluyen en mensajes de error las cabeceras/credenciales ni la URL
completa (que podría llevar tokens en query).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

import httpx

from apps.integration_hub.connectors.base import (
    BaseConnector,
    ConnectorConnectionError,
    ConnectorDataError,
    ConnectorNotSupportedError,
    TestConnectionResult,
)

logger = logging.getLogger(__name__)


class GenericRestConnector(BaseConnector):
    PROVIDER_CODE = "generic_rest"
    PROVIDER_NAME = "Genérico REST"
    # Entidades que este conector sabe normalizar; la disponibilidad real depende
    # además de que estén configuradas en ``configuracion['entidades']``.
    SUPPORTED_ENTITIES = ["contactos", "productos"]

    # ── Capacidad efectiva (config-driven) ────────────────────────────────────

    def supports(self, entidad: str) -> bool:
        configuradas = self._config.get("entidades") or {}
        return entidad in self.SUPPORTED_ENTITIES and entidad in configuradas

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _base_url(self) -> str:
        url = (self._config.get("base_url") or "").strip().rstrip("/")
        if not url:
            raise ConnectorConnectionError(
                "Falta 'base_url' en la configuración del conector genérico."
            )
        return url

    def _request(self, endpoint: str) -> object:
        """GET autenticado a ``base_url + endpoint``; retorna el JSON parseado.

        No incluye cabeceras ni la URL en los mensajes de error (R-CODE-8).
        """
        url = f"{self._base_url()}/{(endpoint or '').lstrip('/')}"
        headers = self._config.get("headers") or {}
        timeout = self._config.get("timeout") or 30
        verify = self._config.get("verify_ssl", True)
        try:
            resp = httpx.get(url, headers=headers, timeout=timeout, verify=verify)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorConnectionError(
                f"HTTP {exc.response.status_code} al leer '{endpoint}' del sistema externo."
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectorConnectionError(
                f"Error de conexión al leer '{endpoint}' del sistema externo: "
                f"{type(exc).__name__}."
            ) from exc
        try:
            return resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ConnectorDataError(
                f"Respuesta no-JSON al leer '{endpoint}'."
            ) from exc

    @staticmethod
    def _extraer_lista(payload, raiz: str | None) -> list:
        """Navega ``raiz`` (dotted) hasta la lista de registros."""
        if raiz:
            for parte in raiz.split("."):
                payload = payload.get(parte) if isinstance(payload, dict) else None
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload
        raise ConnectorDataError("La respuesta del sistema externo no es una lista de registros.")

    @staticmethod
    def _checksum(data: dict) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    def _mapear(self, raw: dict, mapa: dict) -> dict:
        """Aplica el mapa ``campo_canónico → campo_fuente`` sobre un registro."""
        out = {canonico: raw.get(fuente) for canonico, fuente in (mapa or {}).items()}
        out["id_externo"] = str(out.get("id_externo") or raw.get("id") or "")
        out["_checksum"] = self._checksum(raw)
        out["_fuente"] = self.PROVIDER_CODE
        return out

    def _pull_entidad(self, entidad: str, limite: int | None = None) -> list[dict]:
        conf = (self._config.get("entidades") or {}).get(entidad)
        if not conf:
            raise ConnectorNotSupportedError(
                f"El conector genérico no tiene configurada la entidad '{entidad}'."
            )
        endpoint = conf.get("endpoint") or ""
        if not endpoint:
            raise ConnectorDataError(f"Falta 'endpoint' para la entidad '{entidad}'.")

        payload = self._request(endpoint)
        registros = self._extraer_lista(payload, conf.get("raiz"))
        mapa = conf.get("mapa") or {}
        normalizados = [self._mapear(r, mapa) for r in registros]
        if limite:
            normalizados = normalizados[:limite]
        return normalizados

    # ── Conexión ──────────────────────────────────────────────────────────────

    def test_connection(self) -> TestConnectionResult:
        try:
            url = self._base_url()
        except ConnectorConnectionError as exc:
            return TestConnectionResult(success=False, message=str(exc))

        test_endpoint = self._config.get("test_endpoint")
        try:
            if test_endpoint is not None:
                self._request(test_endpoint)
            else:
                resp = httpx.get(
                    url,
                    headers=self._config.get("headers") or {},
                    timeout=self._config.get("timeout") or 30,
                    verify=self._config.get("verify_ssl", True),
                )
                resp.raise_for_status()
            return TestConnectionResult(success=True, message="Conexión REST exitosa.")
        except ConnectorConnectionError as exc:
            return TestConnectionResult(success=False, message=str(exc))
        except httpx.HTTPError as exc:
            return TestConnectionResult(
                success=False, message=f"Fallo de conexión: {type(exc).__name__}."
            )

    def get_version_info(self) -> dict:
        return {
            "provider": self.PROVIDER_CODE,
            "base_url_configurado": bool(self._config.get("base_url")),
            "entidades": sorted((self._config.get("entidades") or {}).keys()),
        }

    # ── Lectura (pull) ────────────────────────────────────────────────────────

    def pull_contactos(self, desde: datetime | None = None, limite: int = 500) -> list[dict]:
        return self._pull_entidad("contactos", limite)

    def pull_productos(self, desde: datetime | None = None, limite: int = 500) -> list[dict]:
        return self._pull_entidad("productos", limite)
