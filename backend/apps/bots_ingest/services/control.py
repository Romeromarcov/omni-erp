"""Servicio multi-tenant del plano de control de bots.

Generaliza el plano de control para cualquier empresa en Omni ERP:
- Los bots corren como servicio hermano (ADR-011), reportan latido periódico y reciben
  su configuración vigente (``habilitado``, ``parametros``, ``chats``, ``mensaje``, ``usuarios``).
- Nunca almacena ni devuelve tokens de Telegram ni llaves de API: cualquier texto libre
  reportado por un bot (p. ej. ``ultimo_error``) se trunca y redacta antes de persistir (R-CODE-8).
- Todo cambio de configuración o autorización de usuarios registra ``antes`` y ``despues`` en
  ``BotBitacora`` acotado a ``id_empresa``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from ..models import BotBitacora, BotLatidoDiario, BotRegistro, BotUsuario, IngestaBot

# Flota estándar disponible para cualquier empresa; empresas también pueden registrar códigos propios.
BOTS_ESTANDAR: dict[str, str] = {
    "pedidos": "Ventas",
    "cobranza": "Cobranzas",
    "compras": "Compras",
    "eventos": "Eventos",
    "tareas": "Tareas",
}
_NOMBRES_TRANSICION: dict[str, str] = {
    **BOTS_ESTANDAR,
    "asana": "Tareas (Asana)",
}

KINDS_POR_BOT: dict[str, tuple[str, ...]] = {
    "pedidos": (
        IngestaBot.Kind.CONTACTO,
        IngestaBot.Kind.COTIZACION,
        IngestaBot.Kind.PEDIDO,
    ),
    "cobranza": (IngestaBot.Kind.PAGO,),
    "compras": (
        IngestaBot.Kind.PAGO_PROVEEDOR,
        IngestaBot.Kind.FACTURA_PROVEEDOR,
        IngestaBot.Kind.PROVEEDOR,
        IngestaBot.Kind.GASTO,
    ),
    "eventos": (IngestaBot.Kind.EVENTO,),
    "tareas": (),
    "asana": (),
}

EN_LINEA_SEGUNDOS = 180
RETENCION_LATIDOS_DIAS = 30

PARAMETROS_POR_DEFECTO: dict[str, Any] = {
    "auto_envio_min": 10,
    "gemini_model": "gemini-2.5-flash",
}
CHATS_POR_DEFECTO: dict[str, int | None] = {"respaldo": None, "grupo": None}
MODELOS_GEMINI_SUGERIDOS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-flash-latest",
    "gemini-pro-latest",
)

ESTADOS_DESTINO = ("ok", "error", "desactivado")
ESTADOS_GEMINI = ("ok", "error", "sin_clave")

_CODIGO_RX = re.compile(r"^[a-z][a-z0-9_-]{1,29}\Z")
_MODELO_RX = re.compile(r"^[a-z0-9][a-z0-9._-]{2,59}\Z")

_SECRETOS = (
    re.compile(r"(?<!\d)\d{6,15}:[A-Za-z0-9_-]{30,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{25,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bcxc_live_[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\b(bearer|capabilitytoken|x-bot-key|x-capability-token)\s*[:=]?\s*[A-Za-z0-9._~+/=-]{12,}"),
)


class DatoControlInvalido(ValueError):
    """Dato inválido recibido en el plano de control (422 legible)."""


def redactar(texto: str) -> str:
    """Oculta cualquier patrón que parezca un token de bot, llave de API o credencial y limpia bytes nulos."""
    limpio = texto.replace("\x00", "")
    for rx in _SECRETOS:
        limpio = rx.sub("[oculto]", limpio)
    return limpio


def validar_codigo_bot(codigo: Any) -> str:
    if not isinstance(codigo, str):
        raise DatoControlInvalido("El código del bot es inválido.")
    limpio = codigo.replace("\x00", "").strip().lower()
    if not _CODIGO_RX.match(limpio):
        raise DatoControlInvalido(
            "El código del bot debe tener entre 2 y 30 caracteres (letras minúsculas, números, guion)."
        )
    return limpio


def validar_lista_bots(codigos: Any) -> list[str]:
    if codigos in (None, []):
        return []
    if not isinstance(codigos, list):
        raise DatoControlInvalido("La lista de bots permitidos debe ser un arreglo.")
    vistos: list[str] = []
    for item in codigos:
        c = validar_codigo_bot(item)
        if c not in vistos:
            vistos.append(c)
    return vistos


def _entero(valor: Any, campo: str, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int | str):
        raise DatoControlInvalido(f"{campo} debe ser un número entero.")
    try:
        n = int(valor)
    except ValueError as exc:
        raise DatoControlInvalido(f"{campo} debe ser un número entero.") from exc
    if not minimo <= n <= maximo:
        raise DatoControlInvalido(f"{campo} debe estar entre {minimo} y {maximo}.")
    return n


def validar_parametros(nuevos: Any) -> dict[str, Any]:
    if not isinstance(nuevos, dict):
        raise DatoControlInvalido("parametros debe ser un objeto.")
    out: dict[str, Any] = {}
    for clave, valor in nuevos.items():
        if clave == "auto_envio_min":
            out[clave] = _entero(valor, "auto_envio_min", 1, 120)
        elif clave == "gemini_model":
            if not isinstance(valor, str):
                raise DatoControlInvalido("gemini_model no es un nombre de modelo válido.")
            modelo = valor.replace("\x00", "").strip()
            if not _MODELO_RX.match(modelo) or redactar(modelo) != modelo:
                raise DatoControlInvalido("gemini_model no es un nombre de modelo válido.")
            out[clave] = modelo
        else:
            raise DatoControlInvalido(f"Parámetro desconocido: {clave}.")
    return out


def validar_chats(nuevos: Any) -> dict[str, int | None]:
    if not isinstance(nuevos, dict):
        raise DatoControlInvalido("chats debe ser un objeto.")
    out: dict[str, int | None] = {}
    for clave, valor in nuevos.items():
        if clave not in CHATS_POR_DEFECTO:
            raise DatoControlInvalido(f"Chat desconocido: {clave}.")
        if valor in (None, ""):
            out[clave] = None
            continue
        n = _entero(valor, f"chats.{clave}", -(10**15), 10**15)
        if n == 0:
            raise DatoControlInvalido(f"chats.{clave} no puede ser 0.")
        out[clave] = n
    return out


def validar_url_panel(valor: Any) -> str:
    if not isinstance(valor, str):
        raise DatoControlInvalido("url_panel debe ser texto.")
    v = valor.replace("\x00", "").strip()
    if not v:
        return ""
    u = urlparse(v)
    if (
        u.scheme not in ("http", "https")
        or not u.netloc
        or u.username
        or u.password
        or redactar(v) != v
        or len(v) > 300
        or any(c.isspace() for c in v)
    ):
        raise DatoControlInvalido("url_panel debe ser una dirección http(s) válida sin credenciales embebidas.")
    return v


def validar_mensaje(valor: Any) -> str:
    if not isinstance(valor, str):
        raise DatoControlInvalido("El mensaje debe ser texto.")
    v = redactar(valor.strip())
    if len(v) > 280:
        raise DatoControlInvalido("El mensaje no puede pasar de 280 caracteres.")
    return v


def _texto_limpio(valor: Any, maximo: int) -> str:
    return redactar(str(valor))[:maximo] if valor is not None else ""


def _contador(valor: Any) -> int:
    if isinstance(valor, bool):
        return 0
    try:
        return max(0, min(int(valor), 10**9))
    except (TypeError, ValueError):
        return 0


def sanear_estado(estado: Any) -> dict[str, Any]:
    if not isinstance(estado, dict):
        estado = {}

    def _opcion(valor: Any, validas: tuple[str, ...], defecto: str) -> str:
        return str(valor) if valor in validas else defecto

    ultimo = estado.get("ultimo_error")
    return {
        "modo": _texto_limpio(estado.get("modo"), 30),
        "gemini": _opcion(estado.get("gemini"), ESTADOS_GEMINI, "sin_clave"),
        "omni": _opcion(estado.get("omni"), ESTADOS_DESTINO, "desactivado"),
        "cxc": _opcion(estado.get("cxc"), ESTADOS_DESTINO, "desactivado"),
        "outbox_pendientes": _contador(estado.get("outbox_pendientes")),
        "mensajes_hoy": _contador(estado.get("mensajes_hoy")),
        "errores_hoy": _contador(estado.get("errores_hoy")),
        "ultimo_error": _texto_limpio(ultimo, 300) if ultimo else None,
    }


def usuario_autorizado_en_bot(bots_usuario: list[str] | None, codigo: str) -> bool:
    """Lista vacía autoriza a todos los bots de la empresa; ``tareas`` y ``asana`` son equivalentes."""
    if not bots_usuario:
        return True
    permitidos = set(bots_usuario)
    if codigo in permitidos:
        return True
    if codigo in ("tareas", "asana") and bool(permitidos & {"tareas", "asana"}):
        return True
    return False


def _nombre_por_defecto(codigo: str) -> str:
    return _NOMBRES_TRANSICION.get(codigo) or codigo.replace("_", " ").replace("-", " ").title()


def _en_linea(ultimo_latido: datetime | None, ahora: datetime) -> bool:
    return ultimo_latido is not None and (ahora - ultimo_latido) < timedelta(seconds=EN_LINEA_SEGUNDOS)


def _serializar_registro(reg: BotRegistro | None, codigo: str, ahora: datetime) -> dict[str, Any]:
    nombre = reg.nombre if reg else _nombre_por_defecto(codigo)
    habilitado = reg.habilitado if reg else True
    parametros = {**PARAMETROS_POR_DEFECTO, **(reg.parametros if reg else {})}
    chats = {**CHATS_POR_DEFECTO, **(reg.chats if reg else {})}
    ultimo = reg.ultimo_latido if reg else None
    return {
        "bot": codigo,
        "nombre": nombre,
        "habilitado": habilitado,
        "en_linea": _en_linea(ultimo, ahora),
        "ultimo_latido": ultimo.isoformat() if ultimo else None,
        "hace_segundos": int((ahora - ultimo).total_seconds()) if ultimo else None,
        "visto_alguna_vez": ultimo is not None,
        "version": reg.version if reg else "",
        "estado": reg.estado if reg else {},
        "parametros": parametros,
        "chats": chats,
        "url_panel": reg.url_panel if reg else "",
        "mensaje": reg.mensaje if reg else "",
        "actualizado_por": reg.actualizado_por if reg else "sistema",
        "actualizado_en": reg.fecha_actualizacion.isoformat() if reg else None,
    }


def _usuarios_empresa(empresa) -> list[BotUsuario]:
    return list(
        BotUsuario.objects.filter(id_empresa=empresa, activo=True, usuario__is_active=True)
        .select_related("usuario")
        .order_by("nombre", "telegram_user_id")
    )


def _usuarios_para_latido(usuarios: list[BotUsuario], codigo: str) -> list[dict[str, Any]]:
    return [
        {
            "telegram_id": u.telegram_user_id,
            "email": u.usuario.email or "",
            "nombre": u.nombre or u.usuario.get_full_name() or u.usuario.username,
        }
        for u in usuarios
        if usuario_autorizado_en_bot(u.bots, codigo)
    ]


def registrar_bitacora(
    *,
    empresa,
    entidad: str,
    accion: str,
    antes: dict[str, Any],
    despues: dict[str, Any],
    actor: str,
) -> BotBitacora:
    return BotBitacora.objects.create(
        id_empresa=empresa,
        entidad=entidad[:80],
        accion=accion[:30],
        antes=antes,
        despues=despues,
        actor=(actor or "sistema")[:150],
    )


def nombre_actor(user) -> str:
    username = getattr(user, "username", "")
    email = getattr(user, "email", "")
    return str(email or username or "sistema")[:150]


@transaction.atomic
def registrar_latido(
    *,
    empresa,
    codigo: str,
    nombre: str = "",
    version: str = "",
    estado: Any = None,
    ahora: datetime | None = None,
) -> dict[str, Any]:
    """Registra el latido de un bot de ``empresa`` y devuelve su configuración vigente."""
    codigo_ok = validar_codigo_bot(codigo)
    ts = ahora or timezone.now()
    estado_limpio = sanear_estado(estado)
    nombre_limpio = _texto_limpio(nombre, 60).strip() or _nombre_por_defecto(codigo_ok)
    version_limpia = _texto_limpio(version, 30).strip()

    reg, creado_reg = BotRegistro.objects.select_for_update().get_or_create(
        id_empresa=empresa,
        codigo=codigo_ok,
        defaults={
            "nombre": nombre_limpio,
            "habilitado": True,
            "parametros": dict(PARAMETROS_POR_DEFECTO),
            "chats": dict(CHATS_POR_DEFECTO),
            "version": version_limpia,
            "estado": estado_limpio,
            "ultimo_latido": ts,
            "actualizado_por": "sistema",
        },
    )
    if not creado_reg:
        reg.activo = True
        reg.nombre = nombre_limpio
        reg.version = version_limpia
        reg.estado = estado_limpio
        reg.ultimo_latido = ts
        reg.save(
            update_fields=[
                "activo",
                "nombre",
                "version",
                "estado",
                "ultimo_latido",
                "fecha_actualizacion",
            ]
        )

    dia = ts.date()
    mensajes_hoy = int(estado_limpio.get("mensajes_hoy", 0))
    errores_hoy = int(estado_limpio.get("errores_hoy", 0))
    diario, creado_dia = BotLatidoDiario.objects.select_for_update().get_or_create(
        id_empresa=empresa,
        codigo=codigo_ok,
        dia=dia,
        defaults={
            "latidos": 1,
            "mensajes": mensajes_hoy,
            "errores": errores_hoy,
            "ultimo": ts,
        },
    )
    if not creado_dia:
        diario.activo = True
        diario.latidos += 1
        diario.mensajes = max(diario.mensajes, mensajes_hoy)
        diario.errores = max(diario.errores, errores_hoy)
        diario.ultimo = ts
        diario.save(
            update_fields=[
                "activo",
                "latidos",
                "mensajes",
                "errores",
                "ultimo",
                "fecha_actualizacion",
            ]
        )

    # Retención lógica de 30 días (R-CODE-6: soft delete, nunca borrado físico).
    corte = dia - timedelta(days=RETENCION_LATIDOS_DIAS)
    BotLatidoDiario.objects.filter(id_empresa=empresa, codigo=codigo_ok, activo=True, dia__lt=corte).update(
        activo=False
    )

    usuarios = _usuarios_empresa(empresa)
    return {
        "habilitado": reg.habilitado,
        "parametros": {**PARAMETROS_POR_DEFECTO, **(reg.parametros or {})},
        "chats": {**CHATS_POR_DEFECTO, **(reg.chats or {})},
        "mensaje": reg.mensaje or None,
        "usuarios": _usuarios_para_latido(usuarios, codigo_ok),
    }


def _codigos_empresa(existentes: dict[str, BotRegistro]) -> list[str]:
    orden = list(BOTS_ESTANDAR.keys())
    for extra in sorted(existentes.keys()):
        if extra not in orden:
            orden.append(extra)
    return orden


def listar_bots(empresa, *, ahora: datetime | None = None) -> list[dict[str, Any]]:
    ts = ahora or timezone.now()
    existentes = {b.codigo: b for b in BotRegistro.objects.filter(id_empresa=empresa, activo=True)}
    usuarios = _usuarios_empresa(empresa)
    salida: list[dict[str, Any]] = []
    for codigo in _codigos_empresa(existentes):
        d = _serializar_registro(existentes.get(codigo), codigo, ts)
        d["n_usuarios"] = sum(1 for u in usuarios if usuario_autorizado_en_bot(u.bots, codigo))
        salida.append(d)
    return salida


def detalle_bot(empresa, codigo: str, *, ahora: datetime | None = None) -> dict[str, Any]:
    codigo_ok = validar_codigo_bot(codigo)
    ts = ahora or timezone.now()
    reg = BotRegistro.objects.filter(id_empresa=empresa, codigo=codigo_ok, activo=True).first()
    d = _serializar_registro(reg, codigo_ok, ts)
    usuarios = _usuarios_empresa(empresa)
    d["usuarios"] = [
        {
            "id_bot_usuario": str(u.id_bot_usuario),
            "telegram_user_id": u.telegram_user_id,
            "email": u.usuario.email or "",
            "nombre": u.nombre or u.usuario.get_full_name() or u.usuario.username,
            "bots": list(u.bots or []),
        }
        for u in usuarios
        if usuario_autorizado_en_bot(u.bots, codigo_ok)
    ]
    kinds = KINDS_POR_BOT.get(codigo_ok, ())
    if kinds:
        ingestas = IngestaBot.objects.filter(id_empresa=empresa, activo=True, kind__in=kinds).select_related(
            "bot_usuario__usuario"
        )[:15]
        d["ingestas_recientes"] = [
            {
                "id_ingesta": str(i.id_ingesta),
                "kind": i.kind,
                "estado": i.estado,
                "fecha_creacion": i.fecha_creacion.isoformat(),
                "odoo_ref": i.odoo_ref,
                "error": i.error,
                "incompleto": i.incompleto,
                "vendedor": i.bot_usuario.usuario.email or i.bot_usuario.usuario.username,
                "auto": i.auto,
            }
            for i in ingestas
        ]
    else:
        d["ingestas_recientes"] = []

    desde = ts.date() - timedelta(days=6)
    latidos = BotLatidoDiario.objects.filter(
        id_empresa=empresa, activo=True, codigo=codigo_ok, dia__gte=desde
    ).order_by("dia")
    d["historial"] = [
        {
            "dia": f.dia.isoformat(),
            "latidos": f.latidos,
            "mensajes": f.mensajes,
            "errores": f.errores,
        }
        for f in latidos
    ]
    d["bitacora"] = listar_bitacora(empresa, entidad=f"bot:{codigo_ok}", limite=20)
    d["modelos_sugeridos"] = list(MODELOS_GEMINI_SUGERIDOS)
    return d


@transaction.atomic
def actualizar_bot(
    *,
    empresa,
    codigo: str,
    cambios: dict[str, Any],
    actor: str,
    ahora: datetime | None = None,
) -> dict[str, Any]:
    codigo_ok = validar_codigo_bot(codigo)
    if not isinstance(cambios, dict):
        raise DatoControlInvalido("Los cambios deben ser un objeto.")

    limpios: dict[str, Any] = {}
    if "habilitado" in cambios and cambios["habilitado"] is not None:
        if not isinstance(cambios["habilitado"], bool):
            raise DatoControlInvalido("habilitado debe ser verdadero o falso.")
        limpios["habilitado"] = cambios["habilitado"]
    if "nombre" in cambios and cambios["nombre"] is not None:
        if not isinstance(cambios["nombre"], str) or not cambios["nombre"].strip():
            raise DatoControlInvalido("El nombre del bot no puede estar vacío.")
        limpios["nombre"] = _texto_limpio(cambios["nombre"].strip(), 100)
    if cambios.get("parametros") is not None:
        limpios["parametros"] = validar_parametros(cambios["parametros"])
    if cambios.get("chats") is not None:
        limpios["chats"] = validar_chats(cambios["chats"])
    if cambios.get("url_panel") is not None:
        limpios["url_panel"] = validar_url_panel(cambios["url_panel"])
    if cambios.get("mensaje") is not None:
        limpios["mensaje"] = validar_mensaje(cambios["mensaje"])
    if not limpios:
        raise DatoControlInvalido("No hay nada que cambiar.")

    ts = ahora or timezone.now()
    actor_str = (actor or "sistema").replace("\x00", "")[:150]
    reg, creado = BotRegistro.objects.select_for_update().get_or_create(
        id_empresa=empresa,
        codigo=codigo_ok,
        defaults={
            "nombre": _nombre_por_defecto(codigo_ok),
            "parametros": dict(PARAMETROS_POR_DEFECTO),
            "chats": dict(CHATS_POR_DEFECTO),
            "actualizado_por": actor_str,
        },
    )
    actual_parametros = {**PARAMETROS_POR_DEFECTO, **((reg.parametros if not creado else None) or {})}
    actual_chats = {**CHATS_POR_DEFECTO, **((reg.chats if not creado else None) or {})}
    actual_estado = {
        "habilitado": reg.habilitado if not creado else True,
        "nombre": reg.nombre if not creado else _nombre_por_defecto(codigo_ok),
        "url_panel": reg.url_panel if not creado else "",
        "mensaje": reg.mensaje if not creado else "",
    }

    antes: dict[str, Any] = {}
    despues: dict[str, Any] = {}
    for campo, nuevo in limpios.items():
        if campo == "parametros":
            diff = {k: v for k, v in nuevo.items() if actual_parametros.get(k) != v}
            if diff:
                antes["parametros"] = {k: actual_parametros.get(k) for k in diff}
                despues["parametros"] = diff
        elif campo == "chats":
            diff = {k: v for k, v in nuevo.items() if actual_chats.get(k) != v}
            if diff:
                antes["chats"] = {k: actual_chats.get(k) for k in diff}
                despues["chats"] = diff
        elif actual_estado.get(campo) != nuevo:
            antes[campo] = actual_estado.get(campo)
            despues[campo] = nuevo

    if not despues:
        return detalle_bot(empresa, codigo_ok, ahora=ts)

    reg.activo = True
    if "habilitado" in despues:
        reg.habilitado = despues["habilitado"]
    if "nombre" in despues:
        reg.nombre = despues["nombre"]
    if "parametros" in despues:
        reg.parametros = {**actual_parametros, **despues["parametros"]}
    if "chats" in despues:
        reg.chats = {**actual_chats, **despues["chats"]}
    if "url_panel" in despues:
        reg.url_panel = despues["url_panel"]
    if "mensaje" in despues:
        reg.mensaje = despues["mensaje"]
    reg.actualizado_por = actor_str
    reg.save()

    registrar_bitacora(
        empresa=empresa,
        entidad=f"bot:{codigo_ok}",
        accion="actualizar",
        antes=antes,
        despues=despues,
        actor=actor_str,
    )
    return detalle_bot(empresa, codigo_ok, ahora=ts)


def listar_bitacora(empresa, *, entidad: str | None = None, limite: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(int(limite), 100))
    qs = BotBitacora.objects.filter(id_empresa=empresa, activo=True)
    if entidad:
        entidad_limpia = entidad.replace("\x00", "").strip()
        if entidad_limpia:
            qs = qs.filter(entidad=entidad_limpia)
    return [
        {
            "id": str(b.id_bot_bitacora),
            "entidad": b.entidad,
            "accion": b.accion,
            "antes": b.antes,
            "despues": b.despues,
            "actor": b.actor,
            "en": b.fecha_creacion.isoformat(),
        }
        for b in qs[:lim]
    ]


def resumen_destinos(empresa, *, ahora: datetime | None = None) -> dict[str, Any]:
    ts = ahora or timezone.now()
    flota = listar_bots(empresa, ahora=ts)
    en_linea = [b for b in flota if b["en_linea"]]

    out: dict[str, Any] = {}
    for destino, desactivado in (
        ("omni", "desactivado"),
        ("cxc", "desactivado"),
        ("gemini", "sin_clave"),
    ):
        reportes = {
            b["bot"]: b["estado"].get(destino)
            for b in en_linea
            if isinstance(b.get("estado"), dict) and b["estado"].get(destino)
        }
        valores = set(reportes.values())
        if not reportes:
            estado = "sin_datos"
        elif "error" in valores:
            estado = "error"
        elif "ok" in valores:
            estado = "ok"
        elif valores == {desactivado}:
            estado = "desactivado" if destino != "gemini" else "sin_clave"
        else:
            estado = "sin_datos"
        out[destino] = {"estado": estado, "por_bot": reportes}

    conteos_raw = dict(
        IngestaBot.objects.filter(id_empresa=empresa, activo=True)
        .values("estado")
        .annotate(n=Count("id_ingesta"))
        .values_list("estado", "n")
    )
    out["outbox_pendientes"] = sum(_contador((b.get("estado") or {}).get("outbox_pendientes")) for b in en_linea)
    out["ingestas"] = {est: int(conteos_raw.get(est, 0)) for est, _lbl in IngestaBot.Estado.choices}
    out["bots_en_linea"] = len(en_linea)
    out["bots_total"] = len(flota)
    return out
