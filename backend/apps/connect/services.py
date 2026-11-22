"""Servicios de dominio para Omni Connect (S2 + S3).

Responsabilidades:
- Resolución pública acotada con ``rls_bypass()`` sobre ``Perfil`` y ``Tarjeta`` activas.
- Registro deduplicado de ``Toque`` bajo ``rls_tenant_context(empresa_id)`` + ``full_clean()``.
- Generación de vCard RFC 6350 con sanitización estricta contra inyección CRLF/NUL.
- Aseguramiento idempotente del ``Pipeline`` predeterminado y sus etapas base.
- Captura pública de ``Lead`` con consentimiento obligatorio, honeypot silencioso,
  notificación in-app y publicación de evento de dominio.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import uuid
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core import rls
from apps.core.exceptions import DomainError
from apps.core.models import Empresa, Usuarios
from apps.crm.models import Etapa, Lead, Pipeline
from apps.crm.services_dedup import resolver_o_vincular_contacto

from .models import Perfil, Tarjeta, Toque
from .validators import (
    BOTONES_URL,
    normalizar_email,
    normalizar_slug,
    normalizar_telefono,
    normalizar_uid_chip,
    validar_botones,
    validar_slug_perfil,
    validar_uid_chip,
)

logger = logging.getLogger("apps.connect")

TEXTO_CONSENTIMIENTO_DEFAULT = (
    "Autorizo el tratamiento de mis datos personales para ser contactado en relación con mi solicitud."
)

TOQUE_DEDUP_TTL_SECONDS = 60

DEFAULT_PIPELINE_NOMBRE = "Ventas"
DEFAULT_ETAPAS: tuple[tuple[str, int, str], ...] = (
    ("Nuevo", 1, Etapa.Tipo.ABIERTA),
    ("Contactado", 2, Etapa.Tipo.ABIERTA),
    ("Calificado", 3, Etapa.Tipo.ABIERTA),
    ("Ganado", 4, Etapa.Tipo.GANADA),
    ("Perdido", 5, Etapa.Tipo.PERDIDA),
)

_VCARD_CTRL_RE = re.compile(r"[\r\n\x00]+")
_SAFE_FILENAME_RE = re.compile(r"[^a-z0-9_-]")


class ConnectError(DomainError):
    """Error de dominio controlado del módulo Omni Connect."""


class PerfilNoEncontradoError(ConnectError):
    """El perfil público o tarjeta solicitada no existe o no está activa."""


class ConsentimientoRequeridoError(ConnectError):
    """El visitante no otorgó consentimiento explícito y válido."""


def _validar_sin_nul(valor: str | None, campo: str) -> str:
    texto = "" if valor is None else str(valor)
    if "\x00" in texto:
        raise DjangoValidationError({campo: "El valor contiene caracteres inválidos."})
    return texto


def _hash_ip(ip_str: str | None, *, salt: str = "") -> str:
    """Calcula HMAC-SHA256 salado de una IP; nunca persiste la IP en claro (máx. 64 hex)."""
    raw_ip = (ip_str or "").strip()
    if not raw_ip:
        return ""
    secret_raw = getattr(settings, "CONNECT_IP_HASH_SECRET", "") or settings.SECRET_KEY
    secret = str(secret_raw).encode("utf-8")
    msg = f"{salt}:{raw_ip}".encode("utf-8") if salt else raw_ip.encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def obtener_ip_cliente(request: Any) -> str:
    """Obtiene la IP del cliente alineada con ``NUM_PROXIES`` para evitar spoofing de XFF."""
    meta = getattr(request, "META", {}) or {}
    remote_addr = str(meta.get("REMOTE_ADDR", "") or "").strip()
    xff = str(meta.get("HTTP_X_FORWARDED_FOR", "") or "").strip()
    if not xff:
        return remote_addr

    from rest_framework.settings import api_settings

    num_proxies = getattr(settings, "NUM_PROXIES", None)
    if num_proxies is None:
        num_proxies = getattr(api_settings, "NUM_PROXIES", None)
    if num_proxies is None:
        return remote_addr
    try:
        proxies = int(num_proxies)
    except (TypeError, ValueError):
        return remote_addr
    if proxies <= 0:
        return remote_addr

    partes = [p.strip() for p in xff.split(",") if p.strip()]
    if not partes:
        return remote_addr
    # Cuenta desde el extremo derecho (último proxy confiable) igual que DRF BaseThrottle.get_ident.
    indice = max(0, len(partes) - proxies)
    return partes[indice]


def clasificar_dispositivo(user_agent: str | None) -> str:
    """Clasifica el User-Agent en ``Toque.Dispositivo`` de forma segura (O(1))."""
    ua = (user_agent or "")[:512].lower()
    if any(tok in ua for tok in ("iphone", "ipad", "ipod")):
        return Toque.Dispositivo.IOS
    if "android" in ua:
        return Toque.Dispositivo.ANDROID
    if any(tok in ua for tok in ("windows nt", "macintosh", "mac os x", "x11", "linux", "cros")):
        return Toque.Dispositivo.ESCRITORIO
    return Toque.Dispositivo.OTRO


def resolver_origen_publico(origen: str | None, *, tiene_tarjeta: bool) -> str:
    """Resuelve el origen público válido: NFC si hay tarjeta activa; si no, QR o ENLACE."""
    if tiene_tarjeta:
        return Toque.Origen.NFC
    limpio = (origen or "").strip().upper()
    if limpio == Toque.Origen.QR:
        return Toque.Origen.QR
    return Toque.Origen.ENLACE


def _sanitizar_botones_publicos(botones: Any) -> list[dict[str, str]]:
    """Valida botones antes de proyectarlos al público; descarta estructuras corruptas."""
    if not isinstance(botones, list):
        return []
    try:
        validar_botones(botones)
    except DjangoValidationError:
        validos: list[dict[str, str]] = []
        for item in botones:
            try:
                validar_botones([item])
            except DjangoValidationError:
                continue
            validos.append(
                {
                    "tipo": str(item["tipo"]),
                    "etiqueta": str(item["etiqueta"]).strip(),
                    "valor": str(item["valor"]).strip(),
                }
            )
        return validos
    return [
        {
            "tipo": str(item["tipo"]),
            "etiqueta": str(item["etiqueta"]).strip(),
            "valor": str(item["valor"]).strip(),
        }
        for item in botones
    ]


def resolver_perfil_publico(slug: str, uid: str | None = None) -> dict[str, Any]:
    """Resuelve un perfil activo (y tarjeta ``ACTIVA`` opcional) bajo ``rls_bypass()`` acotado."""
    _validar_sin_nul(slug, "slug")
    if uid is not None:
        _validar_sin_nul(uid, "uid")

    slug_norm = normalizar_slug(slug)
    try:
        validar_slug_perfil(slug_norm)
    except DjangoValidationError as exc:
        raise PerfilNoEncontradoError("Perfil no encontrado.") from exc

    uid_norm: str | None = None
    if uid is not None and str(uid).strip() != "":
        uid_norm = normalizar_uid_chip(str(uid))
        try:
            validar_uid_chip(uid_norm)
        except DjangoValidationError as exc:
            raise PerfilNoEncontradoError("Perfil no encontrado.") from exc

    with rls.rls_bypass():
        perfil = (
            Perfil.objects.select_related("id_empresa")
            .only(
                "id_perfil",
                "id_empresa_id",
                "usuario_id",
                "slug",
                "nombre_publico",
                "cargo",
                "bio",
                "telefono_publico",
                "email_publico",
                "tema",
                "botones",
                "activo",
                "id_empresa__activo",
                "id_empresa__nombre_comercial",
                "id_empresa__nombre_legal",
            )
            .filter(slug=slug_norm, activo=True, id_empresa__activo=True)
            .first()
        )
        if perfil is None:
            raise PerfilNoEncontradoError("Perfil no encontrado.")

        tarjeta_id: uuid.UUID | None = None
        if uid_norm is not None:
            tarjeta = (
                Tarjeta.objects.only("id_tarjeta", "perfil_id", "id_empresa_id", "estado", "activo")
                .filter(
                    uid_chip=uid_norm,
                    perfil_id=perfil.id_perfil,
                    id_empresa_id=perfil.id_empresa_id,
                    estado=Tarjeta.Estado.ACTIVA,
                    activo=True,
                )
                .first()
            )
            if tarjeta is None:
                raise PerfilNoEncontradoError("Perfil no encontrado.")
            tarjeta_id = tarjeta.id_tarjeta

    empresa_nombre = (perfil.id_empresa.nombre_comercial or perfil.id_empresa.nombre_legal or "").strip()
    return {
        "id_perfil": perfil.id_perfil,
        "id_empresa_id": perfil.id_empresa_id,
        "usuario_id": perfil.usuario_id,
        "slug": perfil.slug,
        "nombre_publico": perfil.nombre_publico,
        "cargo": perfil.cargo,
        "bio": perfil.bio,
        "telefono_publico": perfil.telefono_publico,
        "email_publico": perfil.email_publico,
        "tema": perfil.tema,
        "botones": _sanitizar_botones_publicos(perfil.botones),
        "empresa_nombre": empresa_nombre,
        "tarjeta_id": tarjeta_id,
    }


def registrar_toque_publico(
    *,
    perfil_id: uuid.UUID,
    empresa_id: uuid.UUID,
    tarjeta_id: uuid.UUID | None = None,
    origen: str | None = None,
    user_agent: str = "",
    client_ip: str = "",
) -> Toque | None:
    """Registra un toque deduplicado por 60s en caché bajo ``rls_tenant_context``."""
    origen_resuelto = resolver_origen_publico(origen, tiene_tarjeta=tarjeta_id is not None)
    dispositivo = clasificar_dispositivo(user_agent)
    ip_hash = _hash_ip(client_ip, salt=str(empresa_id))
    dedup_ident = ip_hash or "anon"
    dedup_key = f"connect:toque:dedup:{perfil_id}:{origen_resuelto}:{dedup_ident}"

    if not cache.add(dedup_key, 1, timeout=TOQUE_DEDUP_TTL_SECONDS):
        return None

    with rls.rls_tenant_context([empresa_id]):
        toque = Toque(
            id_empresa_id=empresa_id,
            perfil_id=perfil_id,
            tarjeta_id=tarjeta_id,
            origen=origen_resuelto,
            dispositivo=dispositivo,
            ip_hash=ip_hash,
        )
        toque.full_clean()
        toque.save()
    return toque


def _limpiar_vcard_texto(valor: Any) -> str:
    """Elimina NUL y saltos de línea para impedir inyección de propiedades vCard."""
    texto = "" if valor is None else str(valor)
    return _VCARD_CTRL_RE.sub(" ", texto).strip()


def _escapar_vcard_valor(valor: Any) -> str:
    """Sanitiza caracteres de control y aplica escape RFC 6350 (``, ; \\``)."""
    limpio = _limpiar_vcard_texto(valor)
    limpio = limpio.replace("\\", "\\\\")
    limpio = limpio.replace(";", "\\;")
    limpio = limpio.replace(",", "\\,")
    return limpio


def sanitizar_nombre_archivo_vcard(slug: str) -> str:
    """Sanitiza el nombre de archivo para Content-Disposition (sin CRLF ni comillas)."""
    limpio = _SAFE_FILENAME_RE.sub("", normalizar_slug(slug))[:60]
    return limpio or "contacto"


def generar_vcard(perfil_publico: dict[str, Any]) -> str:
    """Genera una vCard RFC 6350/3.0 escapando caracteres especiales y bloqueando CRLF."""
    nombre_limpio = _limpiar_vcard_texto(perfil_publico.get("nombre_publico", "")) or "Contacto"
    fn = _escapar_vcard_valor(nombre_limpio)

    partes_nombre = nombre_limpio.split()
    if len(partes_nombre) >= 2:
        given = _escapar_vcard_valor(" ".join(partes_nombre[:-1]))
        family = _escapar_vcard_valor(partes_nombre[-1])
        n_prop = f"N:{family};{given};;;"
    else:
        n_prop = f"N:{_escapar_vcard_valor(partes_nombre[0])};;;;"

    lineas = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{fn}",
        n_prop,
    ]

    cargo = _escapar_vcard_valor(perfil_publico.get("cargo", ""))
    if cargo:
        lineas.append(f"TITLE:{cargo}")

    empresa = _escapar_vcard_valor(perfil_publico.get("empresa_nombre", ""))
    if empresa:
        lineas.append(f"ORG:{empresa}")

    telefono = _escapar_vcard_valor(perfil_publico.get("telefono_publico", ""))
    if telefono:
        lineas.append(f"TEL;TYPE=CELL:{telefono}")

    email = _escapar_vcard_valor(perfil_publico.get("email_publico", ""))
    if email:
        lineas.append(f"EMAIL;TYPE=INTERNET:{email}")

    for boton in _sanitizar_botones_publicos(perfil_publico.get("botones", [])):
        if boton["tipo"] in BOTONES_URL:
            url_limpia = _limpiar_vcard_texto(boton["valor"])
            if url_limpia:
                lineas.append(f"URL:{_escapar_vcard_valor(url_limpia)}")

    bio = _escapar_vcard_valor(perfil_publico.get("bio", ""))
    if bio:
        lineas.append(f"NOTE:{bio}")

    lineas.append("END:VCARD")
    return "\r\n".join(lineas) + "\r\n"


def _crear_etapas_por_defecto(empresa: Empresa, pipeline: Pipeline) -> None:
    for nombre, orden, tipo in DEFAULT_ETAPAS:
        etapa = Etapa(
            id_empresa=empresa,
            pipeline=pipeline,
            nombre=nombre,
            orden=orden,
            tipo=tipo,
        )
        etapa.full_clean()
        etapa.save()


@transaction.atomic
def asegurar_pipeline_predeterminado(empresa: Empresa) -> Pipeline:
    """Obtiene o crea idempotentemente el pipeline predeterminado y sus 5 etapas."""
    with rls.rls_tenant_context([empresa.pk]):
        existente = (
            Pipeline.objects.filter(id_empresa=empresa, es_predeterminado=True, activo=True)
            .order_by("fecha_creacion")
            .first()
        )
        if existente is not None:
            if not Etapa.objects.filter(id_empresa=empresa, pipeline=existente, activo=True).exists():
                _crear_etapas_por_defecto(empresa, existente)
            return existente

        nombre_candidato = DEFAULT_PIPELINE_NOMBRE
        if Pipeline.objects.filter(id_empresa=empresa, nombre=nombre_candidato, activo=True).exists():
            nombre_candidato = "Ventas Connect"
            sufijo = 2
            while Pipeline.objects.filter(id_empresa=empresa, nombre=nombre_candidato, activo=True).exists():
                nombre_candidato = f"Ventas Connect {sufijo}"
                sufijo += 1

        try:
            with transaction.atomic():
                pipeline = Pipeline(
                    id_empresa=empresa,
                    nombre=nombre_candidato,
                    es_predeterminado=True,
                )
                pipeline.full_clean()
                pipeline.save()
                _crear_etapas_por_defecto(empresa, pipeline)
                return pipeline
        except IntegrityError:
            # Otro worker ganó la carrera por el pipeline predeterminado.
            existente_concurrencia = Pipeline.objects.filter(
                id_empresa=empresa, es_predeterminado=True, activo=True
            ).first()
            if existente_concurrencia is not None:
                return existente_concurrencia
            raise


def _notificar_lead_capturado(
    *,
    empresa: Empresa,
    propietario_id: uuid.UUID,
    lead: Lead,
    perfil_slug: str,
) -> None:
    """Envía notificación in-app tolerando fallos opcionales sin revertir el lead."""
    try:
        from apps.notificaciones.services import emitir_notificacion

        propietario = Usuarios.objects.filter(pk=propietario_id, is_active=True).first()
        if propietario is None:
            return
        with transaction.atomic():
            emitir_notificacion(
                "CONNECT_LEAD_CAPTURADO",
                empresa,
                propietario,
                {
                    "lead_id": str(lead.id_lead),
                    "nombre_lead": str(lead),
                    "fuente": lead.fuente,
                    "perfil_slug": perfil_slug,
                },
                url_accion="/crm/leads",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo emitir notificación de lead Connect [%s]: %s", lead.id_lead, exc)


def _emitir_evento_lead_capturado(payload: dict[str, Any], empresa_id: str) -> None:
    """Publica el evento de dominio ``crm.lead.capturado`` de forma tolerante a fallos."""
    try:
        from apps.eventos.producer import publicar_evento

        publicar_evento(
            tipo="crm.lead.capturado",
            payload=payload,
            empresa_id=empresa_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo publicar evento crm.lead.capturado: %s", exc)


def _honeypot_activado(datos: dict[str, Any]) -> bool:
    for campo in ("website", "company_url"):
        valor = datos.get(campo)
        if valor is not None and str(valor).strip() != "":
            return True
    return False


def capturar_lead_publico(
    *,
    slug: str,
    datos: dict[str, Any],
    uid: str | None = None,
    client_ip: str = "",  # noqa: ARG001 — reservado para auditoría/extensión S5+
    user_agent: str = "",  # noqa: ARG001
) -> dict[str, Any]:
    """Captura un lead desde el perfil público validando consentimiento y honeypot."""
    for campo in ("nombre", "apellido", "empresa_nombre", "email", "telefono", "mensaje", "consentimiento_texto"):
        if campo in datos and datos[campo] is not None:
            _validar_sin_nul(str(datos[campo]), campo)

    perfil_publico = resolver_perfil_publico(slug, uid=uid)

    if _honeypot_activado(datos):
        logger.info("Honeypot Connect activado para slug=%s (descarte silencioso).", perfil_publico["slug"])
        return {
            "ok": True,
            "mensaje": "Contacto enviado correctamente.",
            "lead_id": None,
        }

    consentimiento_aceptado = datos.get("consentimiento_aceptado")
    consentimiento_texto = str(datos.get("consentimiento_texto") or "").strip()
    if consentimiento_aceptado is not True or not consentimiento_texto:
        raise ConsentimientoRequeridoError(
            "Debe aceptar el consentimiento y proporcionar el texto legal de tratamiento de datos."
        )

    nombre = str(datos.get("nombre") or "").strip()
    if not nombre:
        raise DjangoValidationError({"nombre": "El nombre es obligatorio."})

    apellido = str(datos.get("apellido") or "").strip()
    empresa_nombre = str(datos.get("empresa_nombre") or "").strip()
    email = str(datos.get("email") or "").strip()
    telefono = str(datos.get("telefono") or "").strip()
    mensaje = str(datos.get("mensaje") or "").strip()

    fuente_raw = datos.get("fuente") or datos.get("origen")
    fuente = resolver_origen_publico(
        str(fuente_raw) if fuente_raw is not None else None,
        tiene_tarjeta=perfil_publico["tarjeta_id"] is not None,
    )

    empresa_id = perfil_publico["id_empresa_id"]
    perfil_id = perfil_publico["id_perfil"]
    tarjeta_id = perfil_publico["tarjeta_id"]
    propietario_id = perfil_publico["usuario_id"]

    with rls.rls_tenant_context([empresa_id]):
        with transaction.atomic():
            empresa = Empresa.objects.get(pk=empresa_id)
            pipeline = asegurar_pipeline_predeterminado(empresa)
            etapa = (
                Etapa.objects.filter(
                    id_empresa=empresa,
                    pipeline=pipeline,
                    activo=True,
                    tipo=Etapa.Tipo.ABIERTA,
                )
                .order_by("orden", "fecha_creacion")
                .first()
            )
            if etapa is None:
                raise ConnectError("El pipeline predeterminado no tiene etapas abiertas configuradas.")

            contacto = resolver_o_vincular_contacto(
                empresa,
                nombre=nombre,
                apellido=apellido,
                email=email,
                telefono=telefono,
                empresa_nombre=empresa_nombre,
            )

            lead = Lead(
                id_empresa=empresa,
                nombre=nombre,
                apellido=apellido,
                empresa_nombre=empresa_nombre,
                email=email,
                telefono=telefono,
                email_normalizado=normalizar_email(email),
                telefono_normalizado=normalizar_telefono(telefono),
                mensaje=mensaje,
                fuente=fuente,
                tarjeta_id=tarjeta_id,
                perfil_id=perfil_id,
                pipeline=pipeline,
                etapa=etapa,
                propietario_id=propietario_id,
                contacto=contacto,
                consentimiento_aceptado=True,
                consentimiento_fecha=timezone.now(),
                consentimiento_texto=consentimiento_texto,
            )
            lead.full_clean()
            lead.save()

            _notificar_lead_capturado(
                empresa=empresa,
                propietario_id=propietario_id,
                lead=lead,
                perfil_slug=perfil_publico["slug"],
            )

            event_payload = {
                "lead_id": str(lead.id_lead),
                "fuente": lead.fuente,
                "perfil_id": str(perfil_id),
                "tarjeta_id": str(tarjeta_id) if tarjeta_id else None,
                "pipeline_id": str(pipeline.id_pipeline),
                "etapa_id": str(etapa.id_etapa),
            }
            transaction.on_commit(lambda: _emitir_evento_lead_capturado(event_payload, str(empresa_id)))

    return {
        "ok": True,
        "mensaje": "Contacto enviado correctamente.",
        "lead_id": str(lead.id_lead),
    }


_ADMIN_ROLE_NAMES = ("admin", "administrador", "administrador general")


def usuario_es_admin_empresa(usuario: Any, empresa_id: uuid.UUID | None = None) -> bool:
    """True si ``usuario`` es superusuario Omni, staff o posee rol administrador exacto en la empresa."""
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False
    if getattr(usuario, "es_superusuario_omni", False) or getattr(usuario, "is_superuser", False):
        return True
    if getattr(usuario, "is_staff", False):
        if empresa_id is None:
            return True
        from apps.core.viewsets import get_empresas_visible

        return get_empresas_visible(usuario).filter(pk=empresa_id).exists()

    from apps.core.models import UsuarioRoles
    from django.db.models import Q

    if empresa_id is not None and not usuario.empresas.filter(pk=empresa_id).exists():
        return False

    nombre_q = Q()
    for nombre in _ADMIN_ROLE_NAMES:
        nombre_q |= Q(id_rol__nombre_rol__iexact=nombre)

    qs = UsuarioRoles.objects.filter(
        nombre_q,
        id_usuario=usuario,
        id_rol__activo=True,
    )
    if empresa_id is not None:
        qs = qs.filter(Q(id_rol__id_empresa_id=empresa_id) | Q(id_rol__id_empresa__isnull=True))
    return qs.exists()
