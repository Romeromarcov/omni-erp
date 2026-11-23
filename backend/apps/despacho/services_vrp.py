"""Motor de optimización de rutas VRP y tarifas de flete (Plan 09 Fase 6.2).

Incluye:
- Distancia geodésica Haversine (``Decimal`` cuantizado a 4 decimales).
- Evaluación de reglas de tarifa de flete (FIJA / POR_KG / POR_KM / POR_M3 / POR_PALETA).
- Asignación multi-vehículo por capacidad (kg/m³) + secuenciación Nearest-Neighbor + 2-opt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.almacenes.models import Almacen
from apps.crm.models import DireccionCliente

from .models import Despacho, ParadaEntrega, RutaDespacho, TarifaFlete, Vehiculo, ZonaLogistica

_CERO = Decimal("0")
_Q4 = Decimal("0.0001")
_Q6 = Decimal("0.000001")
_RADIO_TIERRA_KM = 6371.0


class VRPError(Exception):
    """Error de dominio en optimización de rutas o cálculo de fletes."""


def _q4(val: Decimal) -> Decimal:
    return val.quantize(_Q4, rounding=ROUND_HALF_UP)


def _dec(val: Any, default: Decimal | None = None) -> Decimal:
    if val is None or val == "":
        if default is not None:
            return default
        raise VRPError("Valor numérico requerido.")
    if isinstance(val, Decimal):
        return val
    try:
        dec = Decimal(str(val).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise VRPError(f"Valor numérico inválido: {val!r}.") from exc
    if not dec.is_finite():
        raise VRPError(f"Valor numérico no finito: {val!r}.")
    return dec


def _validar_coord(lat: Any, lng: Any) -> tuple[Decimal, Decimal]:
    d_lat = _dec(lat)
    d_lng = _dec(lng)
    if d_lat < Decimal("-90") or d_lat > Decimal("90"):
        raise VRPError(f"Latitud fuera de rango [-90, 90]: {d_lat}.")
    if d_lng < Decimal("-180") or d_lng > Decimal("180"):
        raise VRPError(f"Longitud fuera de rango [-180, 180]: {d_lng}.")
    return d_lat.quantize(_Q6, rounding=ROUND_HALF_UP), d_lng.quantize(_Q6, rounding=ROUND_HALF_UP)


def distancia_haversine_km(lat1: Any, lng1: Any, lat2: Any, lng2: Any) -> Decimal:
    """Calcula la distancia geodésica en kilómetros usando la fórmula Haversine."""
    la1, ln1 = _validar_coord(lat1, lng1)
    la2, ln2 = _validar_coord(lat2, lng2)

    phi1 = math.radians(float(la1))
    phi2 = math.radians(float(la2))
    dphi = math.radians(float(la2 - la1))
    dlmb = math.radians(float(ln2 - ln1))

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(dlmb / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return _q4(Decimal(str(_RADIO_TIERRA_KM * c)))


def calcular_tarifa_flete(
    zona: ZonaLogistica | None,
    *,
    peso_kg: Decimal = _CERO,
    volumen_m3: Decimal = _CERO,
    distancia_km: Decimal = _CERO,
    paletas: Decimal = _CERO,
) -> Decimal:
    """Calcula el flete estimado en USD aplicando la regla activa de la zona."""
    if zona is None:
        return _CERO
    regla = TarifaFlete.objects.filter(id_empresa=zona.id_empresa, id_zona=zona, activo=True).first()
    if regla is None:
        return _q4(_dec(zona.tarifa_base_usd, _CERO))

    base = _dec(regla.monto_base_usd, _CERO)
    unit = _dec(regla.tarifa_unidad_usd, _CERO)
    minimo = _dec(regla.minimo_usd, _CERO)

    factor = _CERO
    if regla.tipo_calculo == "POR_KG":
        factor = _dec(peso_kg, _CERO)
    elif regla.tipo_calculo == "POR_KM":
        factor = _dec(distancia_km, _CERO)
    elif regla.tipo_calculo == "POR_M3":
        factor = _dec(volumen_m3, _CERO)
    elif regla.tipo_calculo == "POR_PALETA":
        factor = _dec(paletas, _CERO)

    total = _q4(base + (unit * factor))
    if minimo > total:
        return _q4(minimo)
    return total


@dataclass
class _DespachoNode:
    despacho: Despacho
    direccion_obj: DireccionCliente | None
    lat: Decimal
    lng: Decimal
    peso_kg: Decimal
    volumen_m3: Decimal
    ventana_inicio: time | None


def _extraer_peso_volumen_despacho(despacho: Despacho) -> tuple[Decimal, Decimal]:
    peso = _CERO
    vol = _CERO
    for det in despacho.detalles.select_related("id_producto"):
        qty = _dec(det.cantidad_despachada, _CERO)
        prod = det.id_producto
        p_u = _dec(getattr(prod, "peso_unitario_kg", None), _CERO)
        v_u = _dec(getattr(prod, "volumen_unitario_m3", None), _CERO)
        peso += qty * p_u
        vol += qty * v_u
    return _q4(peso), _q4(vol)


def _resolver_coord_despacho(
    despacho: Despacho,
    *,
    coords_override: dict[str, tuple[Any, Any]] | None,
    origen_lat: Decimal,
    origen_lng: Decimal,
) -> tuple[DireccionCliente | None, Decimal, Decimal, time | None]:
    if coords_override and str(despacho.pk) in coords_override:
        lat_raw, lng_raw = coords_override[str(despacho.pk)]
        la, ln = _validar_coord(lat_raw, lng_raw)
        return None, la, ln, None

    nota = getattr(despacho, "id_nota_venta", None)
    cliente = getattr(nota, "id_cliente", None) if nota is not None else None
    if cliente is not None:
        direc = (
            DireccionCliente.objects.filter(
                id_empresa=despacho.id_empresa,
                id_cliente=cliente,
                activo=True,
                latitud__isnull=False,
                longitud__isnull=False,
            )
            .order_by("-es_direccion_principal", "-fecha_actualizacion")
            .first()
        )
        if direc is not None:
            la, ln = _validar_coord(direc.latitud, direc.longitud)
            return direc, la, ln, direc.ventana_entrega_inicio

    return None, origen_lat, origen_lng, None


def _costo_ruta(origen_lat: Decimal, origen_lng: Decimal, seq: list[_DespachoNode]) -> Decimal:
    total = _CERO
    cur_lat, cur_lng = origen_lat, origen_lng
    for node in seq:
        total += distancia_haversine_km(cur_lat, cur_lng, node.lat, node.lng)
        cur_lat, cur_lng = node.lat, node.lng
    return total


def _ordenar_nearest_neighbor_y_2opt(
    origen_lat: Decimal,
    origen_lng: Decimal,
    nodos: list[_DespachoNode],
) -> list[_DespachoNode]:
    if len(nodos) <= 1:
        return list(nodos)

    pendientes = list(nodos)
    ruta: list[_DespachoNode] = []
    cur_lat, cur_lng = origen_lat, origen_lng

    while pendientes:
        # Prioriza ventana temprana si existe; desempate por menor distancia al punto actual.
        pendientes.sort(
            key=lambda n: (
                distancia_haversine_km(cur_lat, cur_lng, n.lat, n.lng),
                n.ventana_inicio or time(23, 59),
            )
        )
        sig = pendientes.pop(0)
        ruta.append(sig)
        cur_lat, cur_lng = sig.lat, sig.lng

    # Mejora local 2-opt clásica para eliminar cruces en rutas >= 3 paradas.
    if len(ruta) >= 3:
        mejorado = True
        mejor_dist = _costo_ruta(origen_lat, origen_lng, ruta)
        while mejorado:
            mejorado = False
            for i in range(len(ruta) - 1):
                for j in range(i + 1, len(ruta)):
                    candidata = ruta[:i] + list(reversed(ruta[i : j + 1])) + ruta[j + 1 :]
                    d_cand = _costo_ruta(origen_lat, origen_lng, candidata)
                    if d_cand < mejor_dist:
                        ruta = candidata
                        mejor_dist = d_cand
                        mejorado = True
    return ruta


def _siguiente_codigo_ruta(empresa) -> str:
    # Serializa correlativo contra creación simultánea o manual bloqueando filas existentes.
    usados = set(
        RutaDespacho.objects.select_for_update()
        .filter(id_empresa=empresa, codigo__startswith="RUTA-")
        .values_list("codigo", flat=True)
    )
    n = len(usados) + 1
    while f"RUTA-{n:06d}" in usados:
        n += 1
    return f"RUTA-{n:06d}"


@transaction.atomic
def optimizar_rutas_vrp(
    *,
    empresa,
    almacen_origen: Almacen,
    despachos: list[Despacho],
    vehiculos: list[Vehiculo],
    origen_lat: Any,
    origen_lng: Any,
    fecha_ruta: date | None = None,
    factor_trafico: Any = Decimal("1.00"),
    zona: ZonaLogistica | None = None,
    coords_override: dict[str, tuple[Any, Any]] | None = None,
) -> dict[str, Any]:
    """Asigna despachos a vehículos por capacidad y optimiza la secuencia de paradas (NN + 2-opt)."""
    if almacen_origen.id_empresa_id != empresa.pk or not almacen_origen.activo:
        raise VRPError("El almacén de origen no pertenece a la empresa o está inactivo.")
    if zona is not None and (zona.id_empresa_id != empresa.pk or not zona.activo):
        raise VRPError("La zona logística no pertenece a la empresa o está inactiva.")
    if not despachos:
        raise VRPError("Debe indicar al menos un despacho pendiente para planificar.")
    if not vehiculos:
        raise VRPError("Debe indicar al menos un vehículo disponible para planificar.")

    o_lat, o_lng = _validar_coord(origen_lat, origen_lng)
    f_trafico = _dec(factor_trafico, Decimal("1.00"))
    if f_trafico < Decimal("0.50") or f_trafico > Decimal("5.00"):
        raise VRPError("El factor_trafico debe estar entre 0.50 y 5.00.")

    # Bloqueo pesimista ordenado por PK para prevenir doble asignación concurrente.
    desp_ids = sorted({d.pk for d in despachos})
    veh_ids = sorted({v.pk for v in vehiculos})
    desp_locked_map = {
        d.pk: d
        for d in Despacho.objects.select_for_update(of=("self",))
        .select_related("id_nota_venta", "id_nota_venta__id_cliente")
        .filter(pk__in=desp_ids)
        .order_by("pk")
    }
    veh_locked_map = {
        v.pk: v for v in Vehiculo.objects.select_for_update(of=("self",)).filter(pk__in=veh_ids).order_by("pk")
    }
    desp_en_ruta_activa = set(
        ParadaEntrega.objects.filter(
            id_empresa=empresa,
            id_despacho_id__in=desp_ids,
            activo=True,
            id_ruta__activo=True,
            id_ruta__estado__in=("PLANIFICADA", "EN_CURSO"),
            estado__in=("PENDIENTE", "EN_CAMINO"),
        ).values_list("id_despacho_id", flat=True)
    )

    nodos: list[_DespachoNode] = []
    vistas_desp: set[Any] = set()
    for desp_arg in despachos:
        if desp_arg.pk in vistas_desp:
            continue
        vistas_desp.add(desp_arg.pk)
        desp = desp_locked_map.get(desp_arg.pk, desp_arg)
        if desp.id_empresa_id != empresa.pk or not desp.activo:
            raise VRPError(f"El despacho '{desp.numero_despacho}' no pertenece a la empresa o está inactivo.")
        if desp.estado_despacho != Despacho.ESTADO_PENDIENTE:
            raise VRPError(
                f"El despacho '{desp.numero_despacho}' debe estar PENDIENTE (actual: {desp.estado_despacho})."
            )
        if desp.pk in desp_en_ruta_activa:
            raise VRPError(f"El despacho '{desp.numero_despacho}' ya está asignado a otra ruta activa.")
        peso, vol = _extraer_peso_volumen_despacho(desp)
        direc_obj, d_lat, d_lng, win = _resolver_coord_despacho(
            desp, coords_override=coords_override, origen_lat=o_lat, origen_lng=o_lng
        )
        nodos.append(
            _DespachoNode(
                despacho=desp,
                direccion_obj=direc_obj,
                lat=d_lat,
                lng=d_lng,
                peso_kg=peso,
                volumen_m3=vol,
                ventana_inicio=win,
            )
        )

    vehiculos_activos = []
    vistos_veh: set[Any] = set()
    for veh_arg in vehiculos:
        if veh_arg.pk in vistos_veh:
            continue
        vistos_veh.add(veh_arg.pk)
        veh = veh_locked_map.get(veh_arg.pk, veh_arg)
        if veh.id_empresa_id != empresa.pk or not veh.activo:
            raise VRPError(f"El vehículo '{veh.placa}' no pertenece a la empresa o está inactivo.")
        if veh.estado != "DISPONIBLE":
            raise VRPError(f"El vehículo '{veh.placa}' no está DISPONIBLE (estado: {veh.estado}).")
        vehiculos_activos.append(veh)

    # First-fit decreasing por peso para aprovechar mejor la flota.
    nodos_orden = sorted(nodos, key=lambda n: (n.peso_kg, n.volumen_m3), reverse=True)
    asignaciones: dict[str, list[_DespachoNode]] = {str(v.pk): [] for v in vehiculos_activos}
    uso_peso: dict[str, Decimal] = {str(v.pk): _CERO for v in vehiculos_activos}
    uso_vol: dict[str, Decimal] = {str(v.pk): _CERO for v in vehiculos_activos}
    no_asignados: list[str] = []

    veh_ordenados = sorted(vehiculos_activos, key=lambda v: _dec(v.capacidad_kg), reverse=True)
    for node in nodos_orden:
        colocado = False
        for veh in veh_ordenados:
            vid = str(veh.pk)
            if (uso_peso[vid] + node.peso_kg <= _dec(veh.capacidad_kg)) and (
                uso_vol[vid] + node.volumen_m3 <= _dec(veh.capacidad_m3)
            ):
                asignaciones[vid].append(node)
                uso_peso[vid] += node.peso_kg
                uso_vol[vid] += node.volumen_m3
                colocado = True
                break
        if not colocado:
            no_asignados.append(str(node.despacho.pk))

    rutas_creadas: list[RutaDespacho] = []
    f_ruta = fecha_ruta or timezone.localdate()
    ahora = timezone.now()
    tiempo_serv = zona.tiempo_servicio_min if zona is not None else 15

    for veh in vehiculos_activos:
        vid = str(veh.pk)
        grupo = asignaciones[vid]
        if not grupo:
            continue
        secuencia_optima = _ordenar_nearest_neighbor_y_2opt(o_lat, o_lng, grupo)

        ruta = RutaDespacho.objects.create(
            id_empresa=empresa,
            codigo=_siguiente_codigo_ruta(empresa),
            fecha_ruta=f_ruta,
            id_almacen_origen=almacen_origen,
            origen_lat=o_lat,
            origen_lng=o_lng,
            id_vehiculo=veh,
            id_zona=zona,
            estado="PLANIFICADA",
            peso_total_kg=_q4(uso_peso[vid]),
            volumen_total_m3=_q4(uso_vol[vid]),
        )

        cur_lat, cur_lng = o_lat, o_lng
        dist_total = _CERO
        dur_acum_min = 0
        vel_kmh = _dec(veh.velocidad_promedio_kmh, Decimal("35.00"))

        for idx, node in enumerate(secuencia_optima, start=1):
            tramo_km = distancia_haversine_km(cur_lat, cur_lng, node.lat, node.lng)
            dist_total += tramo_km
            min_viaje = int(
                ((tramo_km / vel_kmh) * Decimal("60") * f_trafico).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            dur_acum_min += min_viaje + tiempo_serv
            eta: datetime = ahora + timedelta(minutes=dur_acum_min)

            ParadaEntrega.objects.create(
                id_empresa=empresa,
                id_ruta=ruta,
                id_despacho=node.despacho,
                id_direccion_cliente=node.direccion_obj,
                secuencia=idx,
                estado="PENDIENTE",
                latitud=node.lat,
                longitud=node.lng,
                direccion_texto=node.despacho.direccion_destino,
                distancia_tramo_km=_q4(tramo_km),
                eta_estimada=eta,
            )
            cur_lat, cur_lng = node.lat, node.lng

        dist_total_q = _q4(dist_total)
        flete_usd = calcular_tarifa_flete(
            zona,
            peso_kg=_q4(uso_peso[vid]),
            volumen_m3=_q4(uso_vol[vid]),
            distancia_km=dist_total_q,
        )
        ruta.distancia_estimada_km = dist_total_q
        ruta.duracion_estimada_min = dur_acum_min
        ruta.costo_flete_estimado_usd = flete_usd
        ruta.save(update_fields=["distancia_estimada_km", "duracion_estimada_min", "costo_flete_estimado_usd"])
        rutas_creadas.append(ruta)

    return {
        "rutas": rutas_creadas,
        "rutas_creadas": len(rutas_creadas),
        "despachos_asignados": sum(r.paradas.count() for r in rutas_creadas),
        "despachos_no_asignados": no_asignados,
    }
