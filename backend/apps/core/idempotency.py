"""
Idempotencia para endpoints de escritura financiera (P1-2 hardening, R9).

En un ERP financiero un doble-submit o un reintento de red NO debe duplicar un
pago, un abono o una factura. Este módulo provee un decorador reutilizable que
envuelve una acción DRF de escritura: si el cliente envía la cabecera
``Idempotency-Key`` y esa clave ya se consumió (mismo tenant + scope), se
reproduce la respuesta original sin re-ejecutar la lógica de negocio.

Diseño:
- La unicidad ``(empresa, scope, clave)`` aísla por tenant (R-CODE-1): dos
  empresas pueden usar la misma cadena de clave sin colisionar.
- La operación corre dentro de ``transaction.atomic`` y el registro de la clave
  se crea en la MISMA transacción que la lógica de negocio: si la vista falla, la
  clave NO queda consumida y un reintento legítimo puede volver a intentar.
- La concurrencia (dos peticiones idénticas en paralelo) se resuelve con la
  restricción ``UniqueConstraint`` de la BD: la segunda inserción lanza
  ``IntegrityError`` y se traduce en la respuesta cacheada de la primera (o 409
  si el snapshot aún no está visible).
- Reuso de clave con payload distinto → 409 (la clave ya identifica otra cosa).
- No se guarda PII ni secretos: solo un hash SHA-256 del payload.

Uso::

    class MiViewSet(...):
        @idempotent("cxc:abonar")
        @action(detail=True, methods=["post"], url_path="abonar")
        def abonar(self, request, pk=None):
            ...

El decorador ``@idempotent`` debe ir POR ENCIMA de ``@action`` para envolver el
handler que DRF invoca. Si la petición no trae cabecera ``Idempotency-Key``, la
acción se ejecuta normalmente (idempotencia opt-in del cliente).
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging

from django.db import IntegrityError, transaction
from rest_framework import status as http_status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

HEADER_NAME = "Idempotency-Key"
_META_KEY = "HTTP_IDEMPOTENCY_KEY"
MAX_CLAVE_LEN = 255


def _hash_payload(data) -> str:
    """SHA-256 hex de una representación canónica y estable del payload."""
    try:
        canonical = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        canonical = repr(data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _empresa_de_request(view, request):
    """
    Resuelve la empresa (tenant) dueña de la operación para scoping de la clave.

    Reusa ``get_empresa_primaria`` (visibilidad multi-tenant del usuario). Si el
    usuario no tiene empresa, devuelve None y el decorador omite la idempotencia
    (la vista decidirá si rechaza por falta de empresa).
    """
    from apps.core.viewsets import get_empresa_primaria

    return get_empresa_primaria(request.user)


def idempotent(scope: str):
    """
    Decorador para acciones DRF de escritura que las hace idempotentes por
    ``Idempotency-Key`` cuando el cliente envía la cabecera.

    Args:
        scope: identificador estable del endpoint (ej. "cxc:abonar"). Forma parte
               de la clave de unicidad, así dos endpoints distintos pueden recibir
               la misma cadena de clave sin colisionar.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(self, request, *args, **kwargs):
            clave = request.META.get(_META_KEY) or request.headers.get(HEADER_NAME)
            if not clave:
                # Idempotencia opt-in: sin cabecera, comportamiento normal.
                return view_func(self, request, *args, **kwargs)

            clave = str(clave).strip()
            if not clave or len(clave) > MAX_CLAVE_LEN:
                return Response(
                    {"error": f"Cabecera {HEADER_NAME} inválida (vacía o demasiado larga)."},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

            empresa = _empresa_de_request(self, request)
            if empresa is None:
                # Sin tenant resoluble no podemos scoping; delega en la vista.
                return view_func(self, request, *args, **kwargs)

            from apps.core.models import ClaveIdempotencia

            payload_hash = _hash_payload(request.data)

            # 1) ¿Ya existe la clave? → reproducir o conflicto por payload distinto.
            existente = ClaveIdempotencia.objects.filter(
                empresa=empresa, scope=scope, clave=clave
            ).first()
            if existente is not None:
                return _respuesta_desde_registro(existente, payload_hash)

            # 2) Primera ejecución: lógica de negocio + persistencia de la clave
            #    en la MISMA transacción atómica.
            try:
                with transaction.atomic():
                    response = view_func(self, request, *args, **kwargs)
                    # Solo persistimos respuestas exitosas (2xx). Un 4xx/5xx no
                    # consume la clave: un reintento legítimo puede reintentar.
                    if 200 <= response.status_code < 300:
                        ClaveIdempotencia.objects.create(
                            empresa=empresa,
                            scope=scope,
                            clave=clave,
                            payload_hash=payload_hash,
                            status_respuesta=response.status_code,
                            cuerpo_respuesta=_json_safe(response.data),
                        )
                    return response
            except IntegrityError:
                # Carrera: otra petición idéntica creó la clave entre el SELECT y
                # el INSERT. La lógica de negocio de ESTA transacción se revierte;
                # reproducimos la respuesta de la ganadora.
                ganadora = ClaveIdempotencia.objects.filter(
                    empresa=empresa, scope=scope, clave=clave
                ).first()
                if ganadora is not None:
                    return _respuesta_desde_registro(ganadora, payload_hash)
                logger.warning(
                    "IntegrityError de idempotencia sin registro visible (scope=%s)", scope
                )
                return Response(
                    {"error": "Conflicto de concurrencia; reintente la operación."},
                    status=http_status.HTTP_409_CONFLICT,
                )

        return wrapper

    return decorator


def _json_safe(data):
    """
    Asegura que el body sea serializable a JSON para guardarlo en JSONField.
    Convierte Decimals/UUIDs/datetimes a str. La vista ya devuelve dinero como
    str (R-CODE-4), así que esto es defensa en profundidad.
    """
    try:
        return json.loads(json.dumps(data, default=str))
    except (TypeError, ValueError):
        return None


def _respuesta_desde_registro(registro, payload_hash: str) -> Response:
    """
    Reproduce la respuesta guardada, o devuelve 409 si la misma clave se está
    reusando con un payload distinto (la clave ya identifica otra operación).
    """
    if registro.payload_hash != payload_hash:
        return Response(
            {
                "error": (
                    "La Idempotency-Key ya fue usada con un cuerpo de petición "
                    "distinto. Use una clave nueva para una operación distinta."
                ),
            },
            status=http_status.HTTP_409_CONFLICT,
        )
    return Response(registro.cuerpo_respuesta, status=registro.status_respuesta)
