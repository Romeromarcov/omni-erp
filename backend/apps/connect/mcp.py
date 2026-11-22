"""Herramientas MCP de Omni Connect (R-CODE-7).

Herramientas expuestas:
  - ``connect_mi_perfil`` (scope ``connect:read``)
  - ``connect_actualizar_perfil`` (scope ``connect:write``)
  - ``connect_analiticas`` (scope ``connect:read``)
  - ``connect_listar_tarjetas`` (scope ``connect:read``)
  - ``connect_gestionar_tarjeta`` (scope ``connect:write``)
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.core.exceptions import sanitize_mcp_error

logger = logging.getLogger("omni.mcp.connect")

_SCOPE = "connect"


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _parse_uuid_mcp(raw: str, campo: str) -> uuid.UUID:
    texto = str(raw)
    if "\x00" in texto:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    limpio = texto.strip()
    if not limpio:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.")
    try:
        return uuid.UUID(limpio)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.") from exc


def _validar_texto_mcp(valor: str | None, campo: str) -> str | None:
    if valor is None:
        return None
    texto = str(valor)
    if "\x00" in texto:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    return texto


def _validar_sin_nul_recursivo_mcp(valor: Any, campo: str) -> None:
    if isinstance(valor, Mapping):
        for key, val in valor.items():
            if "\x00" in str(key):
                raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
            _validar_sin_nul_recursivo_mcp(val, campo)
    elif isinstance(valor, (list, tuple)):
        for item in valor:
            _validar_sin_nul_recursivo_mcp(item, campo)
    elif isinstance(valor, str) and "\x00" in valor:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")


def _resolver_empresa_y_usuario(
    *,
    capability_token: str,
    ctx: dict[str, Any],
    usuario_id: str | None,
):
    from apps.core.models import CapabilityToken, Empresa, Usuarios  # noqa: PLC0415

    empresa_uuid = uuid.UUID(str(ctx["empresa_id"]))
    empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
    if empresa is None:
        raise PermissionError("Empresa no encontrada o inactiva.")

    if usuario_id is not None and str(usuario_id).strip() != "":
        user_uuid = _parse_uuid_mcp(str(usuario_id), "usuario_id")
        usuario = Usuarios.objects.filter(pk=user_uuid, empresas=empresa, is_active=True).first()
        if usuario is None:
            raise PermissionError("El usuario no pertenece a la empresa del token.")
        return empresa, usuario

    token_obj = (
        CapabilityToken.objects.select_related("creado_por")
        .filter(token=capability_token, empresa=empresa, activo=True)
        .first()
    )
    if (
        token_obj is not None
        and token_obj.creado_por is not None
        and token_obj.creado_por.is_active
        and token_obj.creado_por.empresas.filter(pk=empresa.pk).exists()
    ):
        return empresa, token_obj.creado_por

    raise ValueError("Debe especificar usuario_id cuando el token no tiene usuario propietario en la empresa.")


def _serializar_perfil_mcp(perfil) -> dict[str, Any]:
    return {
        "id_perfil": str(perfil.id_perfil),
        "id_empresa": str(perfil.id_empresa_id),
        "usuario_id": str(perfil.usuario_id),
        "slug": perfil.slug,
        "nombre_publico": perfil.nombre_publico,
        "cargo": perfil.cargo,
        "bio": perfil.bio,
        "telefono_publico": perfil.telefono_publico,
        "email_publico": perfil.email_publico,
        "tema": perfil.tema,
        "botones": perfil.botones,
        "plantilla_bloqueada": perfil.plantilla_bloqueada,
        "activo": perfil.activo,
    }


def connect_mi_perfil(
    capability_token: str,
    empresa_id: str | None = None,
    usuario_id: str | None = None,
) -> dict[str, Any]:
    """Consulta el perfil Omni Connect de un usuario en la empresa del token.

    Scope requerido: ``connect:read``
    """
    from apps.connect.models import Perfil  # noqa: PLC0415

    empresa_str: str | None = None
    if empresa_id is not None and str(empresa_id) != "":
        empresa_str = str(_parse_uuid_mcp(str(empresa_id), "empresa_id"))

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_str) as ctx:
        empresa, usuario = _resolver_empresa_y_usuario(
            capability_token=capability_token,
            ctx=ctx,
            usuario_id=usuario_id,
        )
        perfil = Perfil.objects.filter(id_empresa=empresa, usuario=usuario).first()
        if perfil is None:
            return {"error": "Perfil Connect no encontrado para el usuario en la empresa."}

        logger.info(
            "connect_mi_perfil | actor=%s | tenant=%s | perfil=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            perfil.id_perfil,
        )
        return _serializar_perfil_mcp(perfil)


def connect_actualizar_perfil(
    capability_token: str,
    empresa_id: str | None = None,
    usuario_id: str | None = None,
    slug: str | None = None,
    nombre_publico: str | None = None,
    cargo: str | None = None,
    bio: str | None = None,
    telefono_publico: str | None = None,
    email_publico: str | None = None,
    tema: str | None = None,
    botones: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Crea o actualiza el perfil Omni Connect del usuario validando ``full_clean()``.

    Scope requerido: ``connect:write``
    """
    from apps.connect.models import Perfil  # noqa: PLC0415
    from apps.connect.services import usuario_es_admin_empresa  # noqa: PLC0415
    from apps.connect.validators import normalizar_slug  # noqa: PLC0415
    from apps.core.models import CapabilityToken  # noqa: PLC0415

    empresa_str: str | None = None
    if empresa_id is not None and str(empresa_id) != "":
        empresa_str = str(_parse_uuid_mcp(str(empresa_id), "empresa_id"))

    slug_val = _validar_texto_mcp(slug, "slug")
    nombre_val = _validar_texto_mcp(nombre_publico, "nombre_publico")
    cargo_val = _validar_texto_mcp(cargo, "cargo")
    bio_val = _validar_texto_mcp(bio, "bio")
    tel_val = _validar_texto_mcp(telefono_publico, "telefono_publico")
    email_val = _validar_texto_mcp(email_publico, "email_publico")
    tema_val = _validar_texto_mcp(tema, "tema")
    if botones is not None:
        _validar_sin_nul_recursivo_mcp(botones, "botones")

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_str) as ctx:
        empresa, usuario = _resolver_empresa_y_usuario(
            capability_token=capability_token,
            ctx=ctx,
            usuario_id=usuario_id,
        )

        token_obj = (
            CapabilityToken.objects.select_related("creado_por")
            .filter(token=capability_token, empresa=empresa, activo=True)
            .first()
        )
        actor_usuario = token_obj.creado_por if token_obj is not None else None
        actor_es_admin = True if actor_usuario is None else usuario_es_admin_empresa(actor_usuario, empresa.pk)
        if actor_usuario is not None and usuario.pk != actor_usuario.pk and not actor_es_admin:
            raise PermissionError("No tienes permiso para modificar el perfil de otro usuario.")

        try:
            with transaction.atomic():
                perfil = Perfil.objects.filter(id_empresa=empresa, usuario=usuario).first()
                if perfil is None:
                    if not slug_val or not nombre_val:
                        return {"error": "Se requieren slug y nombre_publico para crear el perfil."}
                    perfil = Perfil(
                        id_empresa=empresa,
                        usuario=usuario,
                        slug=normalizar_slug(slug_val),
                        nombre_publico=nombre_val.strip(),
                    )
                else:
                    if perfil.plantilla_bloqueada and tema_val is not None and tema_val != perfil.tema:
                        if not actor_es_admin:
                            raise PermissionError("La plantilla está bloqueada por el administrador.")
                    if slug_val is not None:
                        perfil.slug = normalizar_slug(slug_val)
                    if nombre_val is not None:
                        perfil.nombre_publico = nombre_val.strip()

                if cargo_val is not None:
                    perfil.cargo = cargo_val
                if bio_val is not None:
                    perfil.bio = bio_val
                if tel_val is not None:
                    perfil.telefono_publico = tel_val
                if email_val is not None:
                    perfil.email_publico = email_val
                if tema_val is not None:
                    perfil.tema = tema_val
                if botones is not None:
                    perfil.botones = botones

                perfil.full_clean()
                perfil.save()
        except PermissionError:
            raise
        except (DjangoValidationError, IntegrityError, ValueError) as exc:
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="connect_actualizar_perfil",
                    controlled_types=(DjangoValidationError, ValueError),
                )
            }

        logger.info(
            "connect_actualizar_perfil | actor=%s | tenant=%s | perfil=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            perfil.id_perfil,
        )
        return _serializar_perfil_mcp(perfil)


def _serializar_tarjeta_mcp(tarjeta) -> dict[str, Any]:
    return {
        "id_tarjeta": str(tarjeta.id_tarjeta),
        "id_empresa": str(tarjeta.id_empresa_id),
        "perfil_id": str(tarjeta.perfil_id) if tarjeta.perfil_id else None,
        "perfil_slug": tarjeta.perfil.slug if tarjeta.perfil_id and tarjeta.perfil else None,
        "uid_chip": tarjeta.uid_chip,
        "tipo": tarjeta.tipo,
        "estado": tarjeta.estado,
        "fecha_activacion": tarjeta.fecha_activacion.isoformat() if tarjeta.fecha_activacion else None,
        "notas": tarjeta.notas,
        "activo": tarjeta.activo,
    }


def _resolver_empresa_mcp(ctx: dict[str, Any]):
    from apps.core.models import Empresa  # noqa: PLC0415

    empresa_uuid = uuid.UUID(str(ctx["empresa_id"]))
    empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
    if empresa is None:
        raise PermissionError("Empresa no encontrada o inactiva.")
    return empresa


def connect_analiticas(
    capability_token: str,
    empresa_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    perfil_id: str | None = None,
    dias: int = 30,
) -> dict[str, Any]:
    """Consulta las analíticas agregadas de toques, leads y conversión de Omni Connect.

    Scope requerido: ``connect:read``
    """
    from apps.connect.analytics import obtener_analiticas_connect  # noqa: PLC0415
    from apps.connect.services import ConnectError  # noqa: PLC0415

    empresa_str: str | None = None
    if empresa_id is not None and str(empresa_id) != "":
        empresa_str = str(_parse_uuid_mcp(str(empresa_id), "empresa_id"))

    desde_val = _validar_texto_mcp(desde, "desde")
    hasta_val = _validar_texto_mcp(hasta, "hasta")
    perfil_str: str | None = None
    if perfil_id is not None and str(perfil_id).strip() != "":
        perfil_str = str(_parse_uuid_mcp(str(perfil_id), "perfil_id"))

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_str) as ctx:
        empresa = _resolver_empresa_mcp(ctx)
        try:
            resultado = obtener_analiticas_connect(
                empresa,
                desde=desde_val,
                hasta=hasta_val,
                perfil_id=perfil_str,
                dias=dias,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="connect_analiticas",
                    controlled_types=(ConnectError, ValueError),
                )
            }

        logger.info(
            "connect_analiticas | actor=%s | tenant=%s | toques=%d | leads=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            resultado["total_toques"],
            resultado["total_leads"],
        )
        return resultado


def connect_listar_tarjetas(
    capability_token: str,
    empresa_id: str | None = None,
    estado: str | None = None,
    perfil_id: str | None = None,
    incluir_inactivos: bool = False,
    limite: int = 50,
) -> dict[str, Any]:
    """Lista las tarjetas físicas NFC de Omni Connect de la empresa.

    Scope requerido: ``connect:read``
    """
    from apps.connect.models import Tarjeta  # noqa: PLC0415

    empresa_str: str | None = None
    if empresa_id is not None and str(empresa_id) != "":
        empresa_str = str(_parse_uuid_mcp(str(empresa_id), "empresa_id"))

    estado_val = _validar_texto_mcp(estado, "estado")
    perfil_uuid: uuid.UUID | None = None
    if perfil_id is not None and str(perfil_id).strip() != "":
        perfil_uuid = _parse_uuid_mcp(str(perfil_id), "perfil_id")
    if isinstance(limite, bool):
        raise ValueError("El parámetro 'limite' debe ser un entero válido.")
    tope = max(1, min(int(limite), 200))

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_str) as ctx:
        empresa = _resolver_empresa_mcp(ctx)
        qs = Tarjeta.objects.filter(id_empresa=empresa).select_related("perfil")
        if not incluir_inactivos:
            qs = qs.filter(activo=True)
        if estado_val and estado_val.strip():
            qs = qs.filter(estado=estado_val.strip().upper())
        if perfil_uuid is not None:
            qs = qs.filter(perfil_id=perfil_uuid)
        items = list(qs.order_by("-fecha_creacion")[:tope])
        logger.info(
            "connect_listar_tarjetas | actor=%s | tenant=%s | total=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(items),
        )
        return {
            "tarjetas": [_serializar_tarjeta_mcp(t) for t in items],
            "total": len(items),
        }


def connect_gestionar_tarjeta(
    capability_token: str,
    tarjeta_id: str,
    accion: str,
    empresa_id: str | None = None,
    perfil_id: str | None = None,
    activar: bool = False,
) -> dict[str, Any]:
    """Ejecuta una transición de ciclo de vida sobre una tarjeta NFC de la empresa.

    Acciones soportadas: ``asignar``, ``activar``, ``desactivar``, ``marcar_perdida``.
    Scope requerido: ``connect:write``
    """
    from apps.connect.models import Tarjeta  # noqa: PLC0415
    from apps.connect.services import (  # noqa: PLC0415
        ConnectError,
        activar_tarjeta,
        asignar_tarjeta,
        desactivar_tarjeta,
        marcar_tarjeta_perdida,
    )

    empresa_str: str | None = None
    if empresa_id is not None and str(empresa_id) != "":
        empresa_str = str(_parse_uuid_mcp(str(empresa_id), "empresa_id"))

    tarjeta_uuid = _parse_uuid_mcp(tarjeta_id, "tarjeta_id")
    accion_val = (_validar_texto_mcp(accion, "accion") or "").strip().lower()
    perfil_uuid: uuid.UUID | None = None
    if perfil_id is not None and str(perfil_id).strip() != "":
        perfil_uuid = _parse_uuid_mcp(str(perfil_id), "perfil_id")

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_str) as ctx:
        empresa = _resolver_empresa_mcp(ctx)
        tarjeta = Tarjeta.objects.select_related("perfil").filter(pk=tarjeta_uuid, id_empresa=empresa).first()
        if tarjeta is None:
            return {"error": "Tarjeta no encontrada en la empresa."}

        try:
            if accion_val == "asignar":
                if perfil_uuid is None:
                    return {"error": "Se requiere perfil_id para asignar la tarjeta."}
                actualizada = asignar_tarjeta(tarjeta, perfil_id=perfil_uuid, activar=bool(activar))
            elif accion_val == "activar":
                actualizada = activar_tarjeta(tarjeta)
            elif accion_val == "desactivar":
                actualizada = desactivar_tarjeta(tarjeta)
            elif accion_val in ("marcar_perdida", "marcar-perdida"):
                actualizada = marcar_tarjeta_perdida(tarjeta)
            else:
                return {"error": "Acción no soportada. Use: asignar, activar, desactivar o marcar_perdida."}
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="connect_gestionar_tarjeta",
                    controlled_types=(ConnectError, DjangoValidationError, ValueError),
                )
            }

        logger.info(
            "connect_gestionar_tarjeta | actor=%s | tenant=%s | tarjeta=%s | accion=%s | estado=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            actualizada.id_tarjeta,
            accion_val,
            actualizada.estado,
        )
        return _serializar_tarjeta_mcp(actualizada)


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": connect_mi_perfil,
        "name": "connect_mi_perfil",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": connect_actualizar_perfil,
        "name": "connect_actualizar_perfil",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": connect_analiticas,
        "name": "connect_analiticas",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": connect_listar_tarjetas,
        "name": "connect_listar_tarjetas",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": connect_gestionar_tarjeta,
        "name": "connect_gestionar_tarjeta",
        "scope": f"{_SCOPE}:write",
    },
]
