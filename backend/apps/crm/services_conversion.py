"""Servicios transaccionales para anonimización (S5) y conversión de ``Lead`` (S6)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_ipv46_address
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.auditoria.models import LogAuditoria
from apps.core.models import Contacto, Empresa, Usuarios
from apps.core.viewsets import get_empresas_visible
from apps.fiscal.services import siguiente_numero
from apps.integration_hub.outbox import (
    ENTIDAD_CRM_LEAD,
    EVENTO_CRM_LEAD_ANONIMIZADO,
    EVENTO_CRM_LEAD_CONVERTIDO,
    encolar_evento_outbox,
)

from .models import Cliente, Etapa, Lead, validar_rif
from .services import CrmError, validar_sin_nul_recursivo
from .services_dedup import _advisory_lock_contacto_empresa, resolver_o_vincular_contacto

logger = logging.getLogger("apps.crm")


def _parse_lead_uuid(lead_id: uuid.UUID | str) -> uuid.UUID:
    if isinstance(lead_id, uuid.UUID):
        return lead_id
    texto = str(lead_id or "")
    if "\x00" in texto:
        raise CrmError("El identificador del lead contiene caracteres inválidos.")
    try:
        return uuid.UUID(texto.strip())
    except (ValueError, TypeError) as exc:
        raise CrmError("Identificador de lead inválido.") from exc


def _validar_acceso_usuario_empresa(usuario: Any, empresa_id: uuid.UUID) -> Usuarios | None:
    if usuario is None or not isinstance(usuario, Usuarios) or not usuario.pk:
        return None
    es_super = bool(getattr(usuario, "es_superusuario_omni", False) or getattr(usuario, "is_superuser", False))
    if not es_super and not get_empresas_visible(usuario).filter(pk=empresa_id).exists():
        raise CrmError("El usuario no tiene acceso a la empresa del lead.")
    return usuario


def _mensaje_validation_error(exc: DjangoValidationError) -> str:
    if hasattr(exc, "message_dict"):
        mensajes: list[str] = []
        for campo, errs in exc.message_dict.items():
            for err in errs:
                texto = str(err).strip()
                if texto:
                    mensajes.append(texto if campo == "__all__" else f"{campo}: {texto}")
        if mensajes:
            return " ".join(mensajes)
    if exc.messages:
        return " ".join(str(m).strip() for m in exc.messages if str(m).strip())
    return "Datos inválidos."


def _extraer_ip_valida(request_meta: Mapping[str, Any] | None) -> str | None:
    if not request_meta:
        return None
    candidata = str(request_meta.get("direccion_ip") or request_meta.get("REMOTE_ADDR") or "").strip()
    if not candidata:
        return None
    try:
        validate_ipv46_address(candidata)
    except DjangoValidationError:
        return None
    return candidata


def _extraer_user_agent(request_meta: Mapping[str, Any] | None) -> str | None:
    if not request_meta:
        return None
    ua = str(request_meta.get("navegador_info") or request_meta.get("HTTP_USER_AGENT") or "").strip()
    return ua[:500] if ua else None


def _emitir_evento_crm(tipo: str, payload: dict[str, Any], empresa_id: str, actor_id: str = "system") -> None:
    """Publica evento de dominio CRM de forma tolerante a fallos del broker."""
    try:
        from apps.eventos.producer import publicar_evento  # noqa: PLC0415

        publicar_evento(tipo=tipo, payload={**payload, "actor_id": actor_id}, empresa_id=empresa_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo publicar evento %s: %s", tipo, exc)


def _registrar_auditoria_crm(
    *,
    empresa: Empresa,
    usuario: Usuarios | None,
    lead_id: uuid.UUID,
    tipo_accion: str,
    descripcion: str,
    cambios_json: dict[str, Any],
    request_meta: Mapping[str, Any] | None = None,
) -> LogAuditoria:
    log = LogAuditoria(
        id_empresa=empresa,
        id_usuario=usuario,
        id_entidad_afectada=lead_id,
        nombre_entidad_afectada="crm.Lead",
        modulo="crm",
        tipo_accion=tipo_accion,
        descripcion_accion=descripcion,
        cambios_json=cambios_json,
        direccion_ip=_extraer_ip_valida(request_meta),
        navegador_info=_extraer_user_agent(request_meta),
    )
    log.full_clean()
    log.save()
    return log


def _contacto_es_exclusivo_de_lead(contacto: Contacto, lead: Lead) -> bool:
    """True solo si ``contacto`` no pertenece a cliente/proveedor/empleado/usuario ni a otros leads."""
    if (
        contacto.es_cliente
        or contacto.es_proveedor
        or contacto.es_empleado
        or contacto.es_usuario
        or contacto.usuario_id is not None
    ):
        return False
    if Cliente.objects.filter(contacto=contacto).exists():
        return False
    if Lead.objects.filter(contacto=contacto).exclude(pk=lead.pk).exists():
        return False

    from apps.contabilidad.models import DetalleAsiento  # noqa: PLC0415
    from apps.finanzas.models import AsignacionPago, Pago  # noqa: PLC0415
    from apps.proveedores.models import Proveedor  # noqa: PLC0415
    from apps.rrhh.models import Empleado  # noqa: PLC0415

    if Proveedor.objects.filter(contacto=contacto).exists():
        return False
    if Empleado.objects.filter(contacto=contacto).exists():
        return False
    if Pago.objects.filter(id_contacto=contacto).exists():
        return False
    if AsignacionPago.objects.filter(id_contacto=contacto).exists():
        return False
    if DetalleAsiento.objects.filter(id_contacto=contacto).exists():
        return False
    return True


def _resolver_lead_bloqueado(
    lead_uuid: uuid.UUID,
    usuario: Any,
    empresa_ids: Sequence[uuid.UUID] | None,
) -> Lead:
    # No combinar select_related() con select_for_update(): en PostgreSQL READ COMMITTED,
    # si una transacción concurrente actualiza lead.etapa y commitea, EvalPlanQual
    # re-evalúa el INNER JOIN contra la tupla previa de Etapa y devuelve 0 filas.
    qs = Lead.objects.select_for_update()
    if empresa_ids is not None:
        qs = qs.filter(id_empresa_id__in=list(empresa_ids))
    elif isinstance(usuario, Usuarios) and usuario.pk:
        es_super = bool(getattr(usuario, "es_superusuario_omni", False) or getattr(usuario, "is_superuser", False))
        if not es_super:
            visible_ids = list(get_empresas_visible(usuario).values_list("pk", flat=True))
            qs = qs.filter(id_empresa_id__in=visible_ids)
    lead = qs.filter(pk=lead_uuid).first()
    if lead is None:
        raise CrmError("Lead no encontrado o sin acceso en la empresa.")
    return lead


@transaction.atomic
def anonimizar_lead(
    lead_id: uuid.UUID | str,
    usuario: Any,
    empresa_ids: Sequence[uuid.UUID] | None = None,
    request_meta: Mapping[str, Any] | None = None,
) -> Lead:
    """Suprime la PII de un ``Lead`` (y de su ``Contacto`` exclusivo si aplica) y registra auditoría."""
    lead_uuid = _parse_lead_uuid(lead_id)
    lead = _resolver_lead_bloqueado(lead_uuid, usuario, empresa_ids)
    usuario_valido = _validar_acceso_usuario_empresa(usuario, lead.id_empresa_id)

    if lead.anonimizado:
        raise CrmError("El lead ya fue anonimizado previamente.")
    if not lead.activo:
        raise CrmError("No se puede anonimizar un lead inactivo.")

    contacto_original = lead.contacto
    contacto_exclusivo_anonimizado = False
    contacto_desvinculado = False

    if contacto_original is not None:
        contacto_locked = Contacto.objects.select_for_update().get(pk=contacto_original.pk)
        if _contacto_es_exclusivo_de_lead(contacto_locked, lead):
            contacto_locked.nombre = "Contacto anonimizado"
            contacto_locked.apellido = ""
            contacto_locked.nombre_comercial = ""
            contacto_locked.rif = ""
            contacto_locked.cedula = ""
            contacto_locked.email = ""
            contacto_locked.telefono = ""
            contacto_locked.email_normalizado = ""
            contacto_locked.telefono_normalizado = ""
            contacto_locked.direccion_fiscal = ""
            contacto_locked.latitud = None
            contacto_locked.longitud = None
            contacto_locked.gps_precision_m = None
            contacto_locked.gps_capturado_en = None
            contacto_locked.activo = False
            contacto_locked.full_clean()
            contacto_locked.save()
            contacto_exclusivo_anonimizado = True
        lead.contacto = None
        contacto_desvinculado = True

    lead.nombre = "Contacto anonimizado"
    lead.apellido = ""
    lead.empresa_nombre = ""
    lead.email = ""
    lead.telefono = ""
    lead.email_normalizado = ""
    lead.telefono_normalizado = ""
    lead.mensaje = ""
    lead.anonimizado = True
    lead.fecha_anonimizacion = timezone.now()

    try:
        lead.full_clean()
    except DjangoValidationError as exc:
        raise CrmError(_mensaje_validation_error(exc)) from exc
    lead.save()

    motivo_registrado = bool(request_meta and str(request_meta.get("motivo") or "").strip())
    _registrar_auditoria_crm(
        empresa=lead.id_empresa,
        usuario=usuario_valido,
        lead_id=lead.pk,
        tipo_accion="ANONIMIZAR_LEAD",
        descripcion="Anonimización de PII del lead conforme a derecho al olvido.",
        cambios_json={
            "campos_anonimizados": [
                "nombre",
                "apellido",
                "empresa_nombre",
                "email",
                "telefono",
                "email_normalizado",
                "telefono_normalizado",
                "mensaje",
            ],
            "contacto_desvinculado": contacto_desvinculado,
            "contacto_exclusivo_anonimizado": contacto_exclusivo_anonimizado,
            "motivo_registrado": motivo_registrado,
        },
        request_meta=request_meta,
    )

    actor_str = str(usuario_valido.pk) if usuario_valido is not None else "system"
    empresa_str = str(lead.id_empresa_id)
    lead_pk_str = str(lead.pk)
    # Payload estrictamente sin PII para propagación de derecho al olvido (S7–S9).
    encolar_evento_outbox(
        lead.id_empresa,
        tipo_evento=EVENTO_CRM_LEAD_ANONIMIZADO,
        entidad_tipo=ENTIDAD_CRM_LEAD,
        entidad_id=lead.pk,
        payload={
            "lead_id": lead_pk_str,
            "anonimizado": True,
        },
        clave_idempotencia=f"{EVENTO_CRM_LEAD_ANONIMIZADO}:{lead_pk_str}",
    )
    transaction.on_commit(
        lambda: _emitir_evento_crm("crm.lead.anonimizado", {"lead_id": lead_pk_str}, empresa_str, actor_str)
    )
    return lead


def _parse_decimal_no_negativo(valor: Any, campo: str, default: Decimal = Decimal("0")) -> Decimal:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return default
    try:
        dec = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError) as exc:
        raise CrmError(f"El valor de '{campo}' no es numérico válido.") from exc
    if not dec.is_finite() or dec < 0:
        raise CrmError(f"El valor de '{campo}' debe ser un número no negativo.")
    return dec


def _parse_entero_no_negativo(valor: Any, campo: str, default: int = 0) -> int:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return default
    if isinstance(valor, bool):
        raise CrmError(f"El valor de '{campo}' debe ser entero.")
    try:
        num = int(valor)
    except (TypeError, ValueError) as exc:
        raise CrmError(f"El valor de '{campo}' debe ser entero.") from exc
    if num < 0 or num > 3650:
        raise CrmError(f"El valor de '{campo}' debe estar entre 0 y 3650.")
    return num


def _parse_fecha_opcional(valor: Any, campo: str) -> date | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        parsed = parse_date(valor.strip())
        if parsed is not None:
            return parsed
    raise CrmError(f"La fecha '{campo}' debe tener formato YYYY-MM-DD.")


def _resolver_moneda_cotizacion(empresa: Empresa, moneda_id_raw: Any):
    from apps.finanzas.models import Moneda  # noqa: PLC0415

    visible_q = (
        Q(empresa=empresa) | Q(empresa__isnull=True, es_publica=True) | Q(empresa__isnull=True, es_generica=True)
    )
    if moneda_id_raw is not None and str(moneda_id_raw).strip() != "":
        try:
            moneda_uuid = uuid.UUID(str(moneda_id_raw).strip())
        except (ValueError, TypeError) as exc:
            raise CrmError("El identificador de moneda es inválido.") from exc
        moneda = Moneda.objects.filter(visible_q, pk=moneda_uuid, activo=True).first()
        if moneda is None:
            raise CrmError("La moneda seleccionada no está disponible para la empresa.")
        return moneda

    if empresa.id_moneda_base_id and empresa.id_moneda_base and empresa.id_moneda_base.activo:
        return empresa.id_moneda_base
    if empresa.id_moneda_pais_id and empresa.id_moneda_pais and empresa.id_moneda_pais.activo:
        return empresa.id_moneda_pais
    moneda_fallback = Moneda.objects.filter(visible_q, activo=True).order_by("codigo_iso").first()
    if moneda_fallback is None:
        raise CrmError("La empresa no tiene una moneda activa configurada para crear cotizaciones.")
    return moneda_fallback


def _resolver_contacto_para_conversion(
    *,
    empresa: Empresa,
    lead: Lead,
    razon_social: str,
    nombre_comercial: str | None,
    rif: str,
    email: str,
    telefono: str,
    direccion: str,
    tipo_cliente: str,
    limite_credito: Decimal,
    dias_credito: int,
) -> Contacto:
    contacto: Contacto | None
    if lead.contacto_id is not None:
        contacto = Contacto.objects.select_for_update().get(pk=lead.contacto_id)
        if not contacto.activo:
            raise CrmError("El contacto vinculado al lead está inactivo.")
    else:
        contacto = resolver_o_vincular_contacto(
            empresa,
            nombre=lead.nombre,
            apellido=lead.apellido,
            email=email or lead.email,
            telefono=telefono or lead.telefono,
            empresa_nombre=razon_social,
        )
        if contacto is None:
            contacto = (
                Contacto.objects.select_for_update()
                .filter(id_empresa=empresa, activo=True, rif=rif)
                .order_by("fecha_creacion")
                .first()
            )
        if contacto is None:
            contacto = Contacto(
                id_empresa=empresa,
                tipo_persona="JURIDICA",
                nombre=razon_social[:255],
                nombre_comercial=(nombre_comercial or "")[:255],
                rif=rif,
                email=email[:254],
                telefono=telefono[:50],
                direccion_fiscal=direccion,
                es_cliente=True,
                tipo_credito=tipo_cliente,
                limite_credito=limite_credito,
                dias_credito=dias_credito,
            )

    if not (contacto.nombre or "").strip():
        contacto.nombre = razon_social[:255]
    if not (contacto.nombre_comercial or "").strip() and nombre_comercial:
        contacto.nombre_comercial = nombre_comercial[:255]
    if not (contacto.rif or "").strip():
        contacto.rif = rif
    if not (contacto.email or "").strip() and email:
        contacto.email = email[:254]
    if not (contacto.telefono or "").strip() and telefono:
        contacto.telefono = telefono[:50]
    if not (contacto.direccion_fiscal or "").strip() and direccion:
        contacto.direccion_fiscal = direccion

    contacto.es_cliente = True
    try:
        contacto.full_clean()
    except DjangoValidationError as exc:
        raise CrmError(_mensaje_validation_error(exc)) from exc
    contacto.save()
    return contacto


def _resolver_o_crear_cliente_conversion(
    *,
    empresa: Empresa,
    contacto: Contacto,
    razon_social: str,
    nombre_comercial: str | None,
    rif: str,
    email: str,
    telefono: str,
    direccion: str,
    tipo_cliente: str,
    limite_credito: Decimal,
    dias_credito: int,
    reutilizar_cliente_existente: bool,
) -> tuple[Cliente, Contacto, bool]:
    cliente_por_rif = (
        Cliente.objects.select_for_update(of=("self",))
        .select_related("contacto")
        .filter(id_empresa=empresa, rif=rif)
        .first()
    )
    cliente_por_contacto = (
        Cliente.objects.select_for_update(of=("self",)).filter(id_empresa=empresa, contacto=contacto).first()
    )

    if cliente_por_rif is not None and not cliente_por_rif.activo:
        raise CrmError("Ya existe un cliente inactivo registrado con ese RIF en la empresa.")

    if (
        cliente_por_rif is not None
        and cliente_por_contacto is not None
        and cliente_por_rif.pk != cliente_por_contacto.pk
    ):
        raise CrmError("Conflicto: el contacto del lead ya está vinculado a otro cliente con distinto RIF.")

    if cliente_por_contacto is not None and cliente_por_contacto.rif != rif:
        raise CrmError("El contacto del lead ya está vinculado a un cliente con un RIF distinto.")

    cliente_existente = cliente_por_rif or cliente_por_contacto
    if cliente_existente is not None:
        if not cliente_existente.activo:
            raise CrmError("El cliente vinculado al contacto está inactivo.")
        if not reutilizar_cliente_existente:
            raise CrmError("Ya existe un cliente activo con ese RIF o contacto en la empresa.")
        if cliente_existente.contacto_id is not None and cliente_existente.contacto_id != contacto.pk:
            raise CrmError("Ya existe un cliente activo con ese RIF vinculado a otro contacto.")

        actualizado = False
        if cliente_existente.contacto_id is None:
            cliente_existente.contacto = contacto
            actualizado = True
        if not (cliente_existente.email or "").strip() and email:
            cliente_existente.email = email[:254]
            actualizado = True
        if not (cliente_existente.telefono or "").strip() and telefono:
            cliente_existente.telefono = telefono[:50]
            actualizado = True
        if not (cliente_existente.direccion or "").strip() and direccion:
            cliente_existente.direccion = direccion
            actualizado = True
        if not (cliente_existente.nombre_comercial or "").strip() and nombre_comercial:
            cliente_existente.nombre_comercial = nombre_comercial[:255]
            actualizado = True
        if actualizado:
            try:
                cliente_existente.full_clean()
            except DjangoValidationError as exc:
                raise CrmError(_mensaje_validation_error(exc)) from exc
            cliente_existente.save()
        return cliente_existente, contacto, True

    nuevo_cliente = Cliente(
        id_empresa=empresa,
        razon_social=razon_social[:255],
        nombre_comercial=nombre_comercial[:255] if nombre_comercial else None,
        rif=rif,
        direccion=direccion or None,
        telefono=telefono[:50] or None,
        email=email[:254] or None,
        tipo_cliente=tipo_cliente,
        limite_credito=limite_credito,
        dias_credito=dias_credito,
        contacto=contacto,
    )
    try:
        nuevo_cliente.full_clean()
    except DjangoValidationError as exc:
        raise CrmError(_mensaje_validation_error(exc)) from exc
    nuevo_cliente.save()
    return nuevo_cliente, contacto, False


def _crear_cotizacion_borrador(
    *,
    empresa: Empresa,
    cliente: Cliente,
    lead: Lead,
    datos: Mapping[str, Any],
):
    from apps.ventas.models import Cotizacion  # noqa: PLC0415

    fecha_cot = _parse_fecha_opcional(datos.get("fecha_cotizacion"), "fecha_cotizacion") or timezone.localdate()
    fecha_venc = _parse_fecha_opcional(datos.get("fecha_vencimiento"), "fecha_vencimiento") or (
        fecha_cot + timedelta(days=15)
    )
    if fecha_venc < fecha_cot:
        raise CrmError("La fecha de vencimiento de la cotización no puede ser anterior a la fecha de emisión.")

    moneda = _resolver_moneda_cotizacion(empresa, datos.get("id_moneda"))
    numero = siguiente_numero(empresa, "COTIZACION")
    observaciones = str(datos.get("observaciones_cotizacion") or lead.mensaje or "").strip() or (
        f"Cotización inicial generada desde lead {lead.pk}"
    )

    cotizacion = Cotizacion(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_cotizacion=numero,
        fecha_cotizacion=fecha_cot,
        fecha_vencimiento=fecha_venc,
        estado="BORRADOR",
        monto_total=Decimal("0.0000"),
        id_moneda=moneda,
        observaciones=observaciones,
        referencia_externa=f"crm.Lead:{lead.pk}",
        documento_json={"lead_id": str(lead.pk)},
    )
    try:
        cotizacion.full_clean()
    except DjangoValidationError as exc:
        raise CrmError(_mensaje_validation_error(exc)) from exc
    cotizacion.save()
    return cotizacion


@transaction.atomic
def convertir_lead_a_cliente(
    lead_id: uuid.UUID | str,
    usuario: Any,
    datos_conversion: Mapping[str, Any] | None,
    empresa_ids: Sequence[uuid.UUID] | None = None,
    request_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convierte atómica e idempotentemente un ``Lead`` en ``crm.Cliente`` (+ ``Cotizacion`` opcional)."""
    from apps.ventas.models import Cotizacion  # noqa: PLC0415

    datos = datos_conversion or {}
    try:
        validar_sin_nul_recursivo(datos)
    except DjangoValidationError as exc:
        raise CrmError(_mensaje_validation_error(exc)) from exc

    lead_uuid = _parse_lead_uuid(lead_id)
    lead = _resolver_lead_bloqueado(lead_uuid, usuario, empresa_ids)
    usuario_valido = _validar_acceso_usuario_empresa(usuario, lead.id_empresa_id)

    if lead.anonimizado:
        raise CrmError("No se puede convertir un lead que fue anonimizado.")
    if not lead.activo:
        raise CrmError("No se puede convertir un lead inactivo.")

    if lead.cliente_convertido_id is not None:
        cliente_previo = lead.cliente_convertido
        if cliente_previo is None:
            raise CrmError("El cliente convertido asociado al lead ya no existe.")
        cotizacion_previa = (
            Cotizacion.objects.filter(pk=lead.cotizacion_convertida_id, id_empresa=lead.id_empresa).first()
            if lead.cotizacion_convertida_id
            else None
        )
        return {
            "lead": lead,
            "cliente": cliente_previo,
            "contacto": lead.contacto or cliente_previo.contacto,
            "cotizacion": cotizacion_previa,
            "ya_convertido": True,
        }

    etapa_ganada = (
        Etapa.objects.filter(
            id_empresa=lead.id_empresa,
            pipeline=lead.pipeline,
            activo=True,
            tipo=Etapa.Tipo.GANADA,
        )
        .order_by("orden", "fecha_creacion")
        .first()
    )
    if etapa_ganada is None:
        raise CrmError("El pipeline del lead no tiene una etapa de tipo GANADA activa.")

    razon_social = str(
        datos.get("razon_social") or lead.empresa_nombre or f"{lead.nombre} {lead.apellido}".strip()
    ).strip()
    if not razon_social:
        raise CrmError("La razón social del cliente es obligatoria.")

    rif = str(datos.get("rif") or "").strip().upper()
    if not rif:
        raise CrmError("El RIF del cliente es obligatorio.")
    try:
        validar_rif(rif)
    except DjangoValidationError as exc:
        raise CrmError(_mensaje_validation_error(exc)) from exc

    nombre_comercial_raw = str(
        datos.get("nombre_comercial") if datos.get("nombre_comercial") is not None else lead.empresa_nombre or ""
    ).strip()
    nombre_comercial = nombre_comercial_raw or None
    email = str(datos.get("email") if datos.get("email") is not None else lead.email or "").strip()
    telefono = str(datos.get("telefono") if datos.get("telefono") is not None else lead.telefono or "").strip()
    direccion = str(datos.get("direccion") or "").strip()

    tipo_cliente = str(datos.get("tipo_cliente") or "CONTADO").strip().upper()
    if tipo_cliente not in ("CONTADO", "CREDITO"):
        raise CrmError("El tipo de cliente debe ser CONTADO o CREDITO.")

    limite_credito = _parse_decimal_no_negativo(datos.get("limite_credito"), "limite_credito")
    dias_credito = _parse_entero_no_negativo(datos.get("dias_credito"), "dias_credito")
    reutilizar_cliente = bool(datos.get("reutilizar_cliente_existente", True))
    crear_cotizacion = bool(datos.get("crear_cotizacion", False))

    empresa = lead.id_empresa
    _advisory_lock_contacto_empresa(empresa.pk)

    contacto = _resolver_contacto_para_conversion(
        empresa=empresa,
        lead=lead,
        razon_social=razon_social,
        nombre_comercial=nombre_comercial,
        rif=rif,
        email=email,
        telefono=telefono,
        direccion=direccion,
        tipo_cliente=tipo_cliente,
        limite_credito=limite_credito,
        dias_credito=dias_credito,
    )

    cliente, contacto, cliente_reutilizado = _resolver_o_crear_cliente_conversion(
        empresa=empresa,
        contacto=contacto,
        razon_social=razon_social,
        nombre_comercial=nombre_comercial,
        rif=rif,
        email=email,
        telefono=telefono,
        direccion=direccion,
        tipo_cliente=tipo_cliente,
        limite_credito=limite_credito,
        dias_credito=dias_credito,
        reutilizar_cliente_existente=reutilizar_cliente,
    )

    cotizacion = (
        _crear_cotizacion_borrador(empresa=empresa, cliente=cliente, lead=lead, datos=datos)
        if crear_cotizacion
        else None
    )

    lead.etapa = etapa_ganada
    lead.contacto = contacto
    lead.cliente_convertido = cliente
    lead.fecha_conversion = timezone.now()
    lead.cotizacion_convertida_id = cotizacion.pk if cotizacion is not None else None
    try:
        lead.full_clean()
    except DjangoValidationError as exc:
        raise CrmError(_mensaje_validation_error(exc)) from exc
    lead.save()

    _registrar_auditoria_crm(
        empresa=empresa,
        usuario=usuario_valido,
        lead_id=lead.pk,
        tipo_accion="CONVERTIR_LEAD",
        descripcion=f"Conversión de lead a cliente {cliente.pk}.",
        cambios_json={
            "lead_id": str(lead.pk),
            "cliente_id": str(cliente.pk),
            "contacto_id": str(contacto.pk),
            "etapa_destino_id": str(etapa_ganada.pk),
            "cliente_reutilizado": cliente_reutilizado,
            "cotizacion_id": str(cotizacion.pk) if cotizacion is not None else None,
        },
        request_meta=request_meta,
    )

    actor_str = str(usuario_valido.pk) if usuario_valido is not None else "system"
    empresa_str = str(empresa.pk)
    event_payload = {
        "lead_id": str(lead.pk),
        "cliente_id": str(cliente.pk),
        "cotizacion_id": str(cotizacion.pk) if cotizacion is not None else None,
    }
    encolar_evento_outbox(
        empresa,
        tipo_evento=EVENTO_CRM_LEAD_CONVERTIDO,
        entidad_tipo=ENTIDAD_CRM_LEAD,
        entidad_id=lead.pk,
        payload={
            **event_payload,
            "etapa_id": str(etapa_ganada.pk),
            "etapa_nombre": etapa_ganada.nombre,
            "etapa_tipo": etapa_ganada.tipo,
        },
        clave_idempotencia=f"{EVENTO_CRM_LEAD_CONVERTIDO}:{lead.pk}",
    )
    transaction.on_commit(lambda: _emitir_evento_crm("crm.lead.convertido", event_payload, empresa_str, actor_str))

    return {
        "lead": lead,
        "cliente": cliente,
        "contacto": contacto,
        "cotizacion": cotizacion,
        "ya_convertido": False,
    }
