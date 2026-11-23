"""Servicios transaccionales TMS: ejecución de ruta, GPS, ePOD, cobro, tracking y guía SENIAT."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import quote

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.finanzas.models import MetodoPago, Moneda, Pago

from .delivery_externo import DeliveryExternoError, obtener_proveedor_delivery
from .models import Despacho, ParadaEntrega, RutaDespacho, Vehiculo
from .services import DespachoError, transicionar_despacho
from .services_vrp import _dec, _validar_coord

_CERO = Decimal("0")
_Q4 = Decimal("0.0001")


class TMSError(Exception):
    """Error de dominio en ejecución operativa de rutas TMS y ePOD."""


@transaction.atomic
def actualizar_gps_vehiculo(vehiculo: Vehiculo, *, latitud: Any, longitud: Any) -> Vehiculo:
    """Actualiza las coordenadas GPS actuales de un vehículo validando rangos geográficos."""
    veh_locked = Vehiculo.objects.select_for_update().get(pk=vehiculo.pk)
    try:
        lat, lng = _validar_coord(latitud, longitud)
    except Exception as exc:
        raise TMSError(str(exc)) from exc
    veh_locked.latitud_actual = lat
    veh_locked.longitud_actual = lng
    veh_locked.gps_actualizado_en = timezone.now()
    veh_locked.save(update_fields=["latitud_actual", "longitud_actual", "gps_actualizado_en", "fecha_actualizacion"])
    return veh_locked


@transaction.atomic
def iniciar_ruta_despacho(ruta: RutaDespacho, usuario) -> RutaDespacho:
    """Transiciona la ruta de PLANIFICADA a EN_CURSO, ocupa vehículo y despachos."""
    ruta_locked = (
        RutaDespacho.objects.select_for_update(of=("self",))
        .select_related("id_vehiculo", "id_conductor")
        .get(pk=ruta.pk)
    )
    if ruta_locked.estado != "PLANIFICADA":
        raise TMSError(f"Solo se pueden iniciar rutas PLANIFICADA. Estado actual: {ruta_locked.estado}.")

    paradas = list(
        ruta_locked.paradas.select_for_update(of=("self",)).select_related("id_despacho").order_by("secuencia")
    )
    if not paradas:
        raise TMSError("La ruta no posee paradas asignadas.")

    ahora = timezone.now()
    if ruta_locked.id_vehiculo is not None:
        veh = Vehiculo.objects.select_for_update().get(pk=ruta_locked.id_vehiculo.pk)
        veh.estado = "EN_RUTA"
        veh.save(update_fields=["estado", "fecha_actualizacion"])

    transportista = getattr(ruta_locked.id_conductor, "id_empleado", None)
    for idx, parada in enumerate(paradas):
        desp = parada.id_despacho
        if desp.estado_despacho == Despacho.ESTADO_PENDIENTE:
            try:
                transicionar_despacho(
                    desp,
                    Despacho.ESTADO_EN_RUTA,
                    usuario,
                    transportista=transportista,
                )
            except DespachoError as exc:
                raise TMSError(str(exc)) from exc
        if idx == 0 and parada.estado == "PENDIENTE":
            parada.estado = "EN_CAMINO"
            parada.save(update_fields=["estado", "fecha_actualizacion"])

    ruta_locked.estado = "EN_CURSO"
    ruta_locked.fecha_inicio = ahora
    ruta_locked.save(update_fields=["estado", "fecha_inicio", "fecha_actualizacion"])
    return ruta_locked


@transaction.atomic
def cancelar_ruta_despacho(ruta: RutaDespacho) -> RutaDespacho:
    """Cancela una ruta en estado PLANIFICADA."""
    ruta_locked = RutaDespacho.objects.select_for_update().get(pk=ruta.pk)
    if ruta_locked.estado != "PLANIFICADA":
        raise TMSError(f"Solo se pueden cancelar rutas PLANIFICADA. Estado actual: {ruta_locked.estado}.")
    ruta_locked.estado = "CANCELADA"
    ruta_locked.save(update_fields=["estado", "fecha_actualizacion"])
    return ruta_locked


@transaction.atomic
def registrar_epod_parada(
    parada: ParadaEntrega,
    usuario,
    *,
    resultado: str = "ENTREGADA",
    receptor_nombre: str = "",
    receptor_cedula: str = "",
    firma_base64: str = "",
    foto_url: str = "",
    latitud: Any = None,
    longitud: Any = None,
    observaciones: str = "",
    motivo_rechazo: str = "",
    cobro: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Registra la Prueba de Entrega Digital (ePOD), transiciona el despacho y opcionalmente cobra en sitio."""
    parada_ref = ParadaEntrega.objects.values("id_ruta_id").get(pk=parada.pk)
    # Orden consistente de locks (RutaDespacho -> ParadaEntrega) igual que iniciar_ruta_despacho.
    ruta = RutaDespacho.objects.select_for_update(of=("self",)).get(pk=parada_ref["id_ruta_id"])
    parada_locked = (
        ParadaEntrega.objects.select_for_update(of=("self",))
        .select_related("id_ruta", "id_despacho", "id_despacho__id_nota_venta", "id_empresa")
        .get(pk=parada.pk)
    )
    if parada_locked.estado in ("ENTREGADA", "ENTREGA_PARCIAL", "RECHAZADA"):
        raise TMSError(f"La parada #{parada_locked.secuencia} ya fue cerrada ({parada_locked.estado}).")
    if ruta.estado not in ("PLANIFICADA", "EN_CURSO"):
        raise TMSError(f"La ruta {ruta.codigo} no está activa ({ruta.estado}).")
    if resultado not in ("ENTREGADA", "ENTREGA_PARCIAL", "RECHAZADA"):
        raise TMSError(f"Resultado de parada inválido: {resultado!r}.")

    if ruta.estado == "PLANIFICADA":
        iniciar_ruta_despacho(ruta, usuario)
        ruta.refresh_from_db()

    lat_q, lng_q = (None, None)
    if latitud is not None and longitud is not None:
        try:
            lat_q, lng_q = _validar_coord(latitud, longitud)
        except Exception as exc:
            raise TMSError(str(exc)) from exc

    despacho = parada_locked.id_despacho
    try:
        if resultado == "RECHAZADA":
            if not (motivo_rechazo or "").strip():
                raise TMSError("Debe indicar 'motivo_rechazo' cuando la parada es RECHAZADA.")
            despacho = transicionar_despacho(
                despacho,
                Despacho.ESTADO_DEVUELTO,
                usuario,
                motivo=motivo_rechazo.strip(),
            )
        else:
            if not (receptor_nombre or "").strip():
                raise TMSError("Debe indicar 'receptor_nombre' para confirmar la entrega ePOD.")
            despacho = transicionar_despacho(
                despacho,
                Despacho.ESTADO_ENTREGADO,
                usuario,
                receptor=receptor_nombre.strip(),
                documento_receptor=receptor_cedula.strip(),
                firma_base64=firma_base64,
            )
    except DespachoError as exc:
        raise TMSError(str(exc)) from exc

    pago_obj: Pago | None = None
    monto_cobro = _CERO
    if cobro and resultado != "RECHAZADA":
        try:
            monto_cobro = _dec(cobro.get("monto"), _CERO).quantize(_Q4, rounding=ROUND_HALF_UP)
        except Exception as exc:
            raise TMSError(str(exc)) from exc
        if monto_cobro <= _CERO:
            raise TMSError("El monto de cobro en sitio debe ser mayor a cero.")

        metodo_id = cobro.get("id_metodo_pago")
        moneda_id = cobro.get("id_moneda")
        if not metodo_id or not moneda_id:
            raise TMSError("Método de pago y moneda son obligatorios para cobro en sitio.")
        emp = parada_locked.id_empresa
        metodo = (
            MetodoPago.objects.filter(pk=str(metodo_id), activo=True)
            .filter(Q(es_generico=True) | Q(es_publico=True) | Q(empresa__isnull=True) | Q(empresa=emp))
            .first()
        )
        moneda = (
            Moneda.objects.filter(pk=str(moneda_id), activo=True)
            .filter(Q(es_generica=True) | Q(es_publica=True) | Q(empresa__isnull=True) | Q(empresa=emp))
            .first()
        )
        if metodo is None or moneda is None:
            raise TMSError("Método de pago o moneda inválidos para cobro en sitio.")

        nota = despacho.id_nota_venta
        contacto = getattr(getattr(nota, "id_cliente", None), "contacto", None) if nota else None
        tasa_cobro = _dec(cobro.get("tasa"), Decimal("1.0000")).quantize(_Q4, rounding=ROUND_HALF_UP)

        pago_obj = Pago.objects.create(
            id_empresa=parada_locked.id_empresa,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="NOTA_VENTA" if nota is not None else "CXC",
            id_documento=nota.pk if nota is not None else despacho.pk,
            id_nota_venta=nota,
            fecha_pago=timezone.now(),
            monto=monto_cobro,
            id_moneda=moneda,
            tasa=tasa_cobro,
            id_metodo_pago=metodo,
            referencia=(cobro.get("referencia") or f"EPOD-{despacho.numero_despacho}").strip(),
            observaciones=f"Cobro contra entrega ruta {ruta.codigo} parada #{parada_locked.secuencia}",
        )

    ahora = timezone.now()
    parada_locked.estado = resultado
    parada_locked.fecha_llegada_real = ahora
    parada_locked.epod_receptor_nombre = (receptor_nombre or "").strip()
    parada_locked.epod_receptor_cedula = (receptor_cedula or "").strip()
    parada_locked.epod_firma_base64 = firma_base64 or ""
    parada_locked.epod_foto_url = (foto_url or "").strip()
    parada_locked.epod_latitud = lat_q
    parada_locked.epod_longitud = lng_q
    parada_locked.epod_observaciones = observaciones or ""
    parada_locked.motivo_rechazo = (motivo_rechazo or "").strip()
    parada_locked.monto_cobrado_en_sitio = monto_cobro
    parada_locked.id_pago_cobro = pago_obj
    parada_locked.save()

    # Avanza siguiente parada a EN_CAMINO o cierra ruta si todas completaron.
    pendientes = list(ruta.paradas.filter(estado__in=("PENDIENTE", "EN_CAMINO")).order_by("secuencia"))
    ruta_completada = False
    if not pendientes:
        ruta.estado = "COMPLETADA"
        ruta.fecha_fin = ahora
        ruta.save(update_fields=["estado", "fecha_fin", "fecha_actualizacion"])
        ruta_completada = True
        if ruta.id_vehiculo_id is not None:
            veh = Vehiculo.objects.select_for_update().get(pk=ruta.id_vehiculo_id)
            if veh.estado == "EN_RUTA":
                veh.estado = "DISPONIBLE"
                veh.save(update_fields=["estado", "fecha_actualizacion"])
    elif pendientes[0].estado == "PENDIENTE":
        sig = pendientes[0]
        sig.estado = "EN_CAMINO"
        sig.save(update_fields=["estado", "fecha_actualizacion"])

    return {
        "parada": parada_locked,
        "despacho_estado": despacho.estado_despacho,
        "pago_id": str(pago_obj.pk) if pago_obj is not None else None,
        "ruta_completada": ruta_completada,
    }


@transaction.atomic
def solicitar_delivery_externo_ruta(
    ruta: RutaDespacho,
    *,
    proveedor_codigo: str,
    destino_lat: Any,
    destino_lng: Any,
    direccion_destino: str,
    config: dict[str, str] | None = None,
    transport=None,
) -> dict[str, Any]:
    """Solicita una unidad externa (Uber Direct / Ridery / Yummy / Simulado) y vincula la ruta."""
    ruta_locked = RutaDespacho.objects.select_for_update(of=("self",)).get(pk=ruta.pk)
    if ruta_locked.estado in ("COMPLETADA", "CANCELADA"):
        raise TMSError(f"No se puede asignar delivery externo en estado {ruta_locked.estado}.")
    if ruta_locked.origen_lat is None or ruta_locked.origen_lng is None:
        raise TMSError("La ruta no posee coordenadas de origen para delivery externo.")

    d_lat, d_lng = _validar_coord(destino_lat, destino_lng)
    try:
        adapter = obtener_proveedor_delivery(proveedor_codigo, config=config, transport=transport)
        res = adapter.solicitar_entrega(
            referencia_ruta=ruta_locked.codigo,
            origen_lat=ruta_locked.origen_lat,
            origen_lng=ruta_locked.origen_lng,
            destino_lat=d_lat,
            destino_lng=d_lng,
            direccion_destino=direccion_destino,
            peso_kg=ruta_locked.peso_total_kg or Decimal("1.0000"),
        )
    except DeliveryExternoError as exc:
        raise TMSError(str(exc)) from exc

    ruta_locked.proveedor_delivery_externo = res["proveedor"]
    ruta_locked.referencia_delivery_externo = res["referencia_externa"]
    ruta_locked.tracking_url_externo = res.get("tracking_url", "")
    ruta_locked.save(
        update_fields=[
            "proveedor_delivery_externo",
            "referencia_delivery_externo",
            "tracking_url_externo",
            "fecha_actualizacion",
        ]
    )
    return res


def consultar_tracking_delivery_ruta(
    ruta: RutaDespacho,
    *,
    config: dict[str, str] | None = None,
    transport=None,
) -> dict[str, Any]:
    """Consulta el estado del envío en vivo con el proveedor externo asignado."""
    if not ruta.referencia_delivery_externo or ruta.proveedor_delivery_externo == "PROPIO":
        raise TMSError("La ruta no tiene un envío con proveedor externo asignado.")
    try:
        adapter = obtener_proveedor_delivery(ruta.proveedor_delivery_externo, config=config, transport=transport)
        return adapter.consultar_tracking(referencia_externa=ruta.referencia_delivery_externo)
    except DeliveryExternoError as exc:
        raise TMSError(str(exc)) from exc


@transaction.atomic
def emitir_guia_despacho_seniat(
    ruta: RutaDespacho,
    *,
    proveedor: str = "SIMULADO",
) -> dict[str, Any]:
    """Emite la Guía de Despacho Digital SENIAT (Providencia 000102) desde la ruta."""
    from apps.localizacion_ve.imprenta_digital import ImprentaDigitalError, emitir_en_imprenta_digital

    ruta_locked = RutaDespacho.objects.select_for_update(of=("self",)).get(pk=ruta.pk)
    if ruta_locked.id_guia_imprenta_digital is not None:
        raise TMSError(
            f"La ruta {ruta_locked.codigo} ya tiene Guía de Despacho SENIAT emitida "
            f"(control: {ruta_locked.guia_numero_control})."
        )
    paradas = list(ruta_locked.paradas.select_related("id_despacho").order_by("secuencia"))
    if not paradas:
        raise TMSError("La ruta no posee paradas para emitir Guía de Despacho.")

    payload = {
        "ruta_codigo": ruta_locked.codigo,
        "fecha_ruta": ruta_locked.fecha_ruta.isoformat(),
        "vehiculo_placa": ruta_locked.id_vehiculo.placa if ruta_locked.id_vehiculo else "",
        "conductor_nombre": ruta_locked.id_conductor.nombre_completo if ruta_locked.id_conductor else "",
        "despachos": [p.id_despacho.numero_despacho for p in paradas],
    }
    try:
        doc = emitir_en_imprenta_digital(
            empresa=ruta_locked.id_empresa,
            tipo_documento="GUIA_DESPACHO",
            referencia_documento=ruta_locked.codigo,
            payload=payload,
            proveedor_override=proveedor,
        )
    except ImprentaDigitalError as exc:
        raise TMSError(str(exc)) from exc

    ruta_locked.id_guia_imprenta_digital = doc.id_emision
    ruta_locked.guia_numero_control = doc.numero_control_asignado
    ruta_locked.save(update_fields=["id_guia_imprenta_digital", "guia_numero_control", "fecha_actualizacion"])

    return {
        "id_emision": str(doc.id_emision),
        "numero_control": doc.numero_control_asignado,
        "codigo_validacion": doc.codigo_validacion,
        "url_verificacion": doc.url_verificacion,
        "proveedor": doc.proveedor,
    }


def generar_payload_tracking_whatsapp(parada: ParadaEntrega, base_url: str = "") -> dict[str, Any]:
    """Construye el link público y mensaje listo para WhatsApp del cliente."""
    limpio_base = (base_url or "").strip().rstrip("/")
    if limpio_base and not limpio_base.startswith(("https://", "http://")):
        raise TMSError("La 'base_url' de tracking debe iniciar con http:// o https://.")
    ruta_rel = f"/api/despacho/tracking/{parada.token_tracking}/"
    tracking_url = f"{limpio_base}{ruta_rel}" if limpio_base else ruta_rel
    mensaje = (
        f"Hola! Tu despacho {parada.id_despacho.numero_despacho} va en la parada #{parada.secuencia} "
        f"(estado: {parada.get_estado_display()}). Sigue el recorrido aquí: {tracking_url}"
    )
    return {
        "parada_id": str(parada.pk),
        "token_tracking": str(parada.token_tracking),
        "tracking_url": tracking_url,
        "whatsapp_deeplink": f"https://wa.me/?text={quote(mensaje)}",
        "mensaje": mensaje,
    }


def torre_control_tms(empresa) -> dict[str, Any]:
    """Snapshot de Torre de Control logística para mapa en vivo y KPIs de entrega."""
    rutas_activas = list(
        RutaDespacho.objects.filter(id_empresa=empresa, estado__in=("PLANIFICADA", "EN_CURSO"), activo=True)
        .select_related("id_vehiculo", "id_conductor", "id_zona")
        .prefetch_related("paradas__id_despacho")
    )
    vehiculos = list(Vehiculo.objects.filter(id_empresa=empresa, activo=True).order_by("placa"))

    return {
        "kpis": {
            "rutas_planificadas": sum(1 for r in rutas_activas if r.estado == "PLANIFICADA"),
            "rutas_en_curso": sum(1 for r in rutas_activas if r.estado == "EN_CURSO"),
            "vehiculos_disponibles": sum(1 for v in vehiculos if v.estado == "DISPONIBLE"),
            "vehiculos_en_ruta": sum(1 for v in vehiculos if v.estado == "EN_RUTA"),
            "paradas_pendientes": sum(
                r.paradas.filter(estado__in=("PENDIENTE", "EN_CAMINO")).count() for r in rutas_activas
            ),
        },
        "vehiculos": [
            {
                "id_vehiculo": str(v.pk),
                "placa": v.placa,
                "marca_modelo": v.marca_modelo,
                "estado": v.estado,
                "latitud_actual": str(v.latitud_actual) if v.latitud_actual is not None else None,
                "longitud_actual": str(v.longitud_actual) if v.longitud_actual is not None else None,
                "gps_actualizado_en": v.gps_actualizado_en.isoformat() if v.gps_actualizado_en else None,
            }
            for v in vehiculos
        ],
        "rutas": [
            {
                "id_ruta": str(r.pk),
                "codigo": r.codigo,
                "estado": r.estado,
                "vehiculo": r.id_vehiculo.placa if r.id_vehiculo else None,
                "conductor": r.id_conductor.nombre_completo if r.id_conductor else None,
                "distancia_estimada_km": str(r.distancia_estimada_km),
                "duracion_estimada_min": r.duracion_estimada_min,
                "proveedor_delivery_externo": r.proveedor_delivery_externo,
                "guia_numero_control": r.guia_numero_control,
                "paradas": [
                    {
                        "id_parada": str(p.pk),
                        "secuencia": p.secuencia,
                        "estado": p.estado,
                        "despacho": p.id_despacho.numero_despacho,
                        "latitud": str(p.latitud) if p.latitud is not None else None,
                        "longitud": str(p.longitud) if p.longitud is not None else None,
                        "eta_estimada": p.eta_estimada.isoformat() if p.eta_estimada else None,
                    }
                    for p in r.paradas.all()
                ],
            }
            for r in rutas_activas
        ],
    }
