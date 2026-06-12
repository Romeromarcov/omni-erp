"""
Idempotencia para endpoints de escritura financiera (P1-2 hardening, R9).

En un ERP financiero un doble-submit o un reintento de red NO debe duplicar un
pago, un abono o una factura. Este módulo provee un decorador reutilizable (y un
mixin para ``create`` de ViewSets) que envuelve una acción DRF de escritura: si
el cliente envía la cabecera ``Idempotency-Key`` y esa clave ya se consumió
(mismo tenant + usuario + scope), se reproduce la respuesta original sin
re-ejecutar la lógica de negocio.

Diseño:
- La unicidad ``(empresa, usuario, scope, clave)`` aísla por tenant (R-CODE-1)
  y por usuario: dos empresas (o dos usuarios) pueden usar la misma cadena de
  clave sin colisionar ni leerse las respuestas mutuamente.
- El registro de la clave se INSERTA al inicio, "en vuelo" (status NULL), en la
  MISMA transacción atómica que la lógica de negocio. Una segunda petición
  concurrente con la misma clave se bloquea en el índice único de la BD hasta
  que la primera commitea, y entonces recibe la respuesta de la ganadora (o un
  409 si la ganadora aún no es visible). Si la vista falla, la transacción se
  revierte y la clave NO queda consumida: un reintento legítimo puede reintentar.
- Reuso de clave con payload distinto → 422 (la clave ya identifica otra
  operación; el cliente debe usar una clave nueva).
- Las claves expiran (TTL 24 h) y se purgan de forma perezosa al registrar
  claves nuevas del mismo tenant (sin Celery).
- No se guarda PII ni secretos: solo un hash SHA-256 del payload (no el payload
  en claro) y el body de la respuesta que el propio cliente ya recibió.

Uso con acciones::

    class MiViewSet(...):
        @idempotent("cxc:abonar")
        @action(detail=True, methods=["post"], url_path="abonar")
        def abonar(self, request, pk=None):
            ...

El decorador ``@idempotent`` debe ir POR ENCIMA de ``@action`` para envolver el
handler que DRF invoca. Si la petición no trae cabecera ``Idempotency-Key``, la
acción se ejecuta normalmente (idempotencia opt-in del cliente; no rompe
clientes existentes).

Uso con ``create`` de un ModelViewSet (diff mínimo en la clase)::

    class PagoViewSet(IdempotentCreateMixin, BaseModelViewSet):
        idempotency_scope = "finanzas:pago"
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

HEADER_NAME = "Idempotency-Key"
_META_KEY = "HTTP_IDEMPOTENCY_KEY"
MAX_CLAVE_LEN = 255

#: Tiempo de vida de una clave consumida. Pasado el TTL, la clave se trata como
#: inexistente (un reintento re-ejecuta) y se purga de la tabla.
TTL = timedelta(hours=24)


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

            usuario = request.user if request.user.is_authenticated else None
            payload_hash = _hash_payload(request.data)
            filtro = {
                "empresa": empresa,
                "usuario": usuario,
                "scope": scope,
                "clave": clave,
            }

            # 1) Camino rápido: la clave ya fue consumida → reproducir (o 422).
            existente = (
                ClaveIdempotencia.objects.filter(**filtro)
                .filter(expira_en__gt=timezone.now())
                .first()
            )
            if existente is not None:
                return _respuesta_desde_registro(existente, payload_hash)

            # 2) Primera ejecución: se inserta la clave "en vuelo" ANTES de la
            #    lógica de negocio, en la misma transacción. Una petición gemela
            #    concurrente se bloquea en el índice único hasta nuestro commit.
            with transaction.atomic():
                # Limpieza perezosa de claves vencidas del tenant (TTL) dentro
                # de la transacción: si la petición falla, la purga se revierte.
                ClaveIdempotencia.purgar_expiradas(empresa)
                try:
                    with transaction.atomic():  # savepoint para el INSERT
                        registro = ClaveIdempotencia.objects.create(
                            payload_hash=payload_hash,
                            status_respuesta=None,
                            expira_en=timezone.now() + TTL,
                            **filtro,
                        )
                except IntegrityError:
                    # Carrera de doble-submit: otra petición idéntica ganó el
                    # INSERT y ya commiteó. Reproducimos su respuesta.
                    ganadora = (
                        ClaveIdempotencia.objects.select_for_update()
                        .filter(**filtro)
                        .first()
                    )
                    if ganadora is not None and ganadora.status_respuesta is not None:
                        return _respuesta_desde_registro(ganadora, payload_hash)
                    logger.warning(
                        "Carrera de idempotencia sin respuesta visible (scope=%s)", scope
                    )
                    return Response(
                        {"error": "Operación en curso con la misma Idempotency-Key; reintente."},
                        status=http_status.HTTP_409_CONFLICT,
                    )

                response = view_func(self, request, *args, **kwargs)
                # Solo persistimos respuestas exitosas (2xx). Un 4xx/5xx no
                # consume la clave: un reintento legítimo puede reintentar.
                if 200 <= response.status_code < 300:
                    registro.status_respuesta = response.status_code
                    registro.cuerpo_respuesta = _json_safe(response.data)
                    registro.save(update_fields=["status_respuesta", "cuerpo_respuesta"])
                else:
                    registro.delete()
                return response

        return wrapper

    return decorator


class IdempotentCreateMixin:
    """
    Mixin para ModelViewSets cuyo ``create`` debe ser idempotente por
    ``Idempotency-Key`` (opt-in del cliente). Diff mínimo en el ViewSet::

        class PagoViewSet(IdempotentCreateMixin, BaseModelViewSet):
            idempotency_scope = "finanzas:pago"
    """

    #: Identificador estable del endpoint; si no se define se deriva del basename.
    idempotency_scope: str | None = None

    def create(self, request, *args, **kwargs):
        scope = self.idempotency_scope or f"{getattr(self, 'basename', type(self).__name__)}:create"

        @idempotent(scope)
        def _create(view, req, *a, **kw):
            return super(IdempotentCreateMixin, view).create(req, *a, **kw)

        return _create(self, request, *args, **kwargs)


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
    Reproduce la respuesta guardada; 422 si la misma clave se está reusando con
    un payload distinto (la clave ya identifica otra operación); 409 si la
    operación original sigue "en vuelo" (sin respuesta commiteada).
    """
    if registro.payload_hash != payload_hash:
        return Response(
            {
                "error": (
                    "La Idempotency-Key ya fue usada con un cuerpo de petición "
                    "distinto. Use una clave nueva para una operación distinta."
                ),
            },
            status=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if registro.status_respuesta is None:
        return Response(
            {"error": "Operación en curso con la misma Idempotency-Key; reintente."},
            status=http_status.HTTP_409_CONFLICT,
        )
    return Response(registro.cuerpo_respuesta, status=registro.status_respuesta)
