"""Puerto ProveedorImprentaDigital (Providencia SENIAT 000102/000121) + adaptadores Simulado y Unidigital."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.db import transaction


class ImprentaDigitalError(ValueError):
    """Error controlado en la comunicación o emisión ante Imprenta Digital."""


class ProveedorImprentaDigital(ABC):
    """Puerto abstracto de Imprenta Digital autorizada por el SENIAT."""

    @abstractmethod
    def emitir_documento(
        self,
        *,
        empresa,
        tipo_documento: str,
        referencia_documento: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    @abstractmethod
    def anular_documento(self, *, empresa, numero_control: str, motivo: str = "") -> dict[str, Any]: ...

    @abstractmethod
    def consultar_estado(self, *, empresa, numero_control: str) -> dict[str, Any]: ...


class SimuladoImprentaAdapter(ProveedorImprentaDigital):
    """Adaptador determinista para QA/desarrollo sin credenciales reales de imprenta."""

    def emitir_documento(
        self,
        *,
        empresa,
        tipo_documento: str,
        referencia_documento: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        from apps.fiscal.models import ConfiguracionFiscalEmpresa
        from apps.fiscal.services import siguiente_numero

        cfg = ConfiguracionFiscalEmpresa.objects.filter(id_empresa=empresa).first()
        serie = (cfg.imprenta_digital_serie if cfg else "00") or "00"
        sec = siguiente_numero(empresa, "GUIA_DESPACHO" if tipo_documento == "GUIA_DESPACHO" else "FACTURA")
        digitos = "".join(ch for ch in str(sec) if ch.isdigit()) or "1"
        nro_ctrl = f"{serie}-{int(digitos[-8:]):08d}"
        digest = hashlib.sha256(
            f"{empresa.pk}:{tipo_documento}:{referencia_documento}:{nro_ctrl}".encode()
        ).hexdigest()
        return {
            "proveedor": "SIMULADO",
            "numero_control": nro_ctrl,
            "codigo_validacion": digest[:32].upper(),
            "url_verificacion": f"https://imprenta-qa.omni-erp.local/verificar/{nro_ctrl}",
            "estado": "EMITIDO",
            "payload_enviado": {
                "tipo_documento": tipo_documento,
                "referencia_documento": referencia_documento,
                "serie": serie,
                **dict(payload or {}),
            },
            "respuesta_proveedor": {"modo": "simulado", "status": "ok"},
        }

    def anular_documento(self, *, empresa, numero_control: str, motivo: str = "") -> dict[str, Any]:
        return {"proveedor": "SIMULADO", "numero_control": numero_control, "estado": "ANULADO", "motivo": motivo}

    def consultar_estado(self, *, empresa, numero_control: str) -> dict[str, Any]:
        return {"proveedor": "SIMULADO", "numero_control": numero_control, "estado": "EMITIDO"}


def _default_https_transport(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 15
) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ImprentaDigitalError("El endpoint de Imprenta Digital debe usar HTTPS.")
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:  # nosec B310 — scheme validado a https arriba
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except (HTTPError, URLError, ValueError) as exc:
        raise ImprentaDigitalError(f"Error al comunicarse con Imprenta Digital: {exc}") from exc


class UnidigitalImprentaAdapter(ProveedorImprentaDigital):
    """Adaptador Unidigital compatible con Providencia 000102/000121."""

    _TIPO_DOC_MAP = {
        "FACTURA": "01",
        "NOTA_DEBITO": "02",
        "NOTA_CREDITO": "03",
        "GUIA_DESPACHO": "04",
    }

    def __init__(self, *, base_url: str = "", transport: Callable[..., dict[str, Any]] | None = None):
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.transport = transport or _default_https_transport

    def _endpoint(self, empresa, suffix: str) -> str:
        from apps.fiscal.models import ConfiguracionFiscalEmpresa

        url = self.base_url
        if not url and empresa is not None:
            cfg = ConfiguracionFiscalEmpresa.objects.filter(id_empresa=empresa).first()
            url = str(getattr(cfg, "imprenta_digital_url", "") or "").strip().rstrip("/")
        if not url:
            raise ImprentaDigitalError(
                "No hay URL configurada para el proveedor Unidigital en ConfiguracionFiscalEmpresa."
            )
        return f"{url}/{suffix.lstrip('/')}"

    def emitir_documento(
        self,
        *,
        empresa,
        tipo_documento: str,
        referencia_documento: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        endpoint = self._endpoint(empresa, "v1/documentos/emitir")
        req_payload = {
            "rif_emisor": getattr(empresa, "identificador_fiscal", "") or "",
            "tipo_documento_seniat": self._TIPO_DOC_MAP.get(tipo_documento, "01"),
            "referencia": referencia_documento,
            "datos": dict(payload or {}),
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        resp = self.transport(endpoint, req_payload, headers, timeout=15)
        nro_ctrl = str(resp.get("numero_control") or "").strip()
        if not nro_ctrl:
            raise ImprentaDigitalError("Unidigital no retornó 'numero_control'.")
        return {
            "proveedor": "UNIDIGITAL",
            "numero_control": nro_ctrl,
            "codigo_validacion": str(resp.get("codigo_validacion") or ""),
            "url_verificacion": str(resp.get("url_verificacion") or ""),
            "estado": "EMITIDO",
            "payload_enviado": req_payload,
            "respuesta_proveedor": resp,
        }

    def anular_documento(self, *, empresa, numero_control: str, motivo: str = "") -> dict[str, Any]:
        endpoint = self._endpoint(empresa, "v1/documentos/anular")
        resp = self.transport(
            endpoint,
            {"numero_control": numero_control, "motivo": motivo},
            {"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        return {"proveedor": "UNIDIGITAL", "numero_control": numero_control, "estado": "ANULADO", "respuesta": resp}

    def consultar_estado(self, *, empresa, numero_control: str) -> dict[str, Any]:
        endpoint = self._endpoint(empresa, "v1/documentos/consultar")
        resp = self.transport(
            endpoint,
            {"numero_control": numero_control},
            {"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        return {
            "proveedor": "UNIDIGITAL",
            "numero_control": numero_control,
            "estado": str(resp.get("estado") or "EMITIDO"),
            "respuesta": resp,
        }


def obtener_proveedor_imprenta_digital(
    empresa,
    *,
    proveedor_override: str | None = None,
    transport: Callable[..., dict[str, Any]] | None = None,
) -> ProveedorImprentaDigital:
    from apps.fiscal.models import ConfiguracionFiscalEmpresa

    prov = str(proveedor_override or "").strip().upper()
    cfg = ConfiguracionFiscalEmpresa.objects.filter(id_empresa=empresa).first()
    if not prov:
        prov = str(getattr(cfg, "imprenta_digital_proveedor", "") or "SIMULADO").strip().upper() or "SIMULADO"

    if prov == "SIMULADO":
        return SimuladoImprentaAdapter()
    if prov == "UNIDIGITAL":
        return UnidigitalImprentaAdapter(
            base_url=str(getattr(cfg, "imprenta_digital_url", "") or ""),
            transport=transport,
        )
    raise ImprentaDigitalError(f"Proveedor de Imprenta Digital no soportado aún: '{prov}'.")


@transaction.atomic
def emitir_en_imprenta_digital(
    *,
    empresa,
    tipo_documento: str,
    referencia_documento: str,
    payload: dict[str, Any] | None = None,
    proveedor_override: str | None = None,
    transport: Callable[..., dict[str, Any]] | None = None,
):
    from apps.fiscal.models import DocumentoImprentaDigital

    tipo_u = str(tipo_documento or "").strip().upper()
    if tipo_u not in {"FACTURA", "NOTA_CREDITO", "NOTA_DEBITO", "GUIA_DESPACHO"}:
        raise ImprentaDigitalError(f"Tipo de documento inválido para imprenta digital: '{tipo_documento}'.")

    adapter = obtener_proveedor_imprenta_digital(empresa, proveedor_override=proveedor_override, transport=transport)
    res = adapter.emitir_documento(
        empresa=empresa,
        tipo_documento=tipo_u,
        referencia_documento=str(referencia_documento).strip(),
        payload=dict(payload or {}),
    )
    doc = DocumentoImprentaDigital.objects.create(
        id_empresa=empresa,
        proveedor=res["proveedor"],
        tipo_documento=tipo_u,
        referencia_documento=str(referencia_documento).strip(),
        numero_control_asignado=res["numero_control"],
        codigo_validacion=res["codigo_validacion"],
        url_verificacion=res["url_verificacion"],
        estado="EMITIDO",
        payload_enviado=res["payload_enviado"],
        respuesta_proveedor=res["respuesta_proveedor"],
    )
    return doc


@transaction.atomic
def anular_en_imprenta_digital(
    documento,
    *,
    motivo: str = "",
    transport: Callable[..., dict[str, Any]] | None = None,
):
    from apps.fiscal.models import DocumentoImprentaDigital

    locked = DocumentoImprentaDigital.objects.select_for_update().get(pk=documento.pk)
    if locked.estado == "ANULADO":
        raise ImprentaDigitalError("El documento de imprenta digital ya está anulado.")
    adapter = obtener_proveedor_imprenta_digital(
        locked.id_empresa, proveedor_override=locked.proveedor, transport=transport
    )
    adapter.anular_documento(
        empresa=locked.id_empresa,
        numero_control=locked.numero_control_asignado,
        motivo=motivo,
    )
    locked.estado = "ANULADO"
    locked.save(update_fields=["estado", "fecha_actualizacion"])
    return locked
