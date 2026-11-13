"""Handlers por tipo de borrador. Cada uno devuelve ``Resultado`` o lanza ``HandlerError``.

``HandlerError`` = el borrador no puede procesarse (el bot lo muestra y conserva el borrador para
corregirlo); no deja registro. Los datos faltantes *tolerables* (pagos) se devuelven en ``incompleto``.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.activaciones import services as activ
from apps.core.models import Contacto
from apps.crm.models import (
    Cliente,
    DireccionCliente,
    Etapa,
    Lead,
    Pipeline,
    validar_rif,
)
from apps.fiscal.services import siguiente_numero
from apps.inventario.models import Producto
from apps.ventas.models import (
    Cotizacion,
    DetalleCotizacion,
    DetallePedido,
    DetallePrecio,
    ListaPrecio,
    Pedido,
)


class HandlerError(Exception):
    def __init__(
        self, mensaje: str, status: int = 422, faltan: list[str] | None = None
    ):
        super().__init__(mensaje)
        self.status = status
        self.faltan = faltan or []


@dataclass
class Ctx:
    empresa: object
    usuario: object  # vendedor (core.Usuarios)
    payload: dict
    fuente: dict


@dataclass
class Resultado:
    resultado: dict = field(default_factory=dict)
    incompleto: list[str] = field(default_factory=list)
    estado: str = "PROCESADO"


# ── utilidades ───────────────────────────────────────────────────────────────


def _vacio(v) -> bool:
    return v in (None, "", [], {})


def _exigir(payload: dict, campos: list[str]) -> None:
    faltan = [c for c in campos if _vacio(payload.get(c))]
    if faltan:
        raise HandlerError(
            f"Faltan datos obligatorios: {', '.join(faltan)}.", faltan=faltan
        )


def _digitos(tel: str) -> str:
    return re.sub(r"\D", "", tel or "")


def _dec(v, nombre="valor") -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError) as e:
        raise HandlerError(f"{nombre} inválido: {v!r}.") from e


def _normalizar_rif(rif: str) -> str:
    """``j-12345678-9`` / ``J 123456789`` → ``J-123456789`` (formato que valida Omni: letra, guion, dígitos)."""
    m = re.match(r"^\s*([VJEGBPvjegbp])[-\s]?([0-9][0-9\-\s]*)\s*$", rif or "")
    if not m:
        raise HandlerError(
            "RIF inválido: usa letra (V/J/E/G/B/P) y números, p. ej. J-123456789.",
            faltan=["rif"],
        )
    return f"{m.group(1).upper()}-{re.sub(r'[^0-9]', '', m.group(2))}"


def _gps(ub: dict | None) -> dict:
    if not ub:
        return {}
    try:
        lat, lon = Decimal(str(ub["latitud"])), Decimal(str(ub["longitud"]))
    except (KeyError, InvalidOperation) as e:
        raise HandlerError("Ubicación GPS inválida.") from e
    if not (Decimal(-90) <= lat <= 90 and Decimal(-180) <= lon <= 180):
        raise HandlerError("Ubicación GPS fuera de rango.")
    prec = ub.get("precision_m")
    return {
        "latitud": round(lat, 6),
        "longitud": round(lon, 6),
        "gps_precision_m": round(Decimal(str(prec)), 2) if prec is not None else None,
        "gps_capturado_en": timezone.now(),
    }


def _buscar_cliente(empresa, nombre: str | None = None, rif: str | None = None):
    qs = Cliente.objects.filter(id_empresa=empresa, activo=True)
    if rif:
        try:
            candidatos = {rif.strip(), _normalizar_rif(rif)}
        except HandlerError:
            candidatos = {rif.strip()}
        c = (
            qs.filter(rif__in=candidatos).first()
            or qs.filter(rif__iexact=rif.strip()).first()
        )
        if c:
            return c
    if nombre:
        n = nombre.strip()
        return qs.filter(
            Q(razon_social__iexact=n) | Q(nombre_comercial__iexact=n)
        ).first()
    return None


def _cliente_para(empresa, nombre: str, rif: str | None = None) -> Cliente:
    """Cliente existente (por RIF o nombre) o uno *provisional* (RIF ``PEND-…``) que el pedido completa."""
    c = _buscar_cliente(empresa, nombre, rif)
    if c:
        return c
    contacto = Contacto.objects.filter(
        id_empresa=empresa, nombre__iexact=nombre.strip()
    ).first()
    if contacto is None:
        contacto = Contacto.objects.create(
            id_empresa=empresa, nombre=nombre.strip(), es_cliente=True
        )
    return Cliente.objects.create(
        id_empresa=empresa,
        razon_social=nombre.strip(),
        rif=f"PEND-{uuid.uuid4().hex[:8].upper()}",
        contacto=contacto,
        documento_json={"provisional": True},
    )


def _lista_de(cliente: Cliente, empresa):
    if cliente.contacto_id and cliente.contacto.lista_precio_id:
        return cliente.contacto.lista_precio
    return ListaPrecio.objects.filter(
        id_empresa=empresa, activo=True, es_referencia=True
    ).first()


def _producto(empresa, texto: str):
    qs = Producto.objects.filter(id_empresa=empresa, activo=True, es_vendible=True)
    t = texto.strip()
    p = qs.filter(Q(sku__iexact=t) | Q(nombre_producto__iexact=t)).first()
    if p:
        return p
    cand = list(qs.filter(nombre_producto__icontains=t)[:2])
    return cand[0] if len(cand) == 1 else None  # ambiguo → sin resolver


def _resolver_lineas(empresa, lineas: list[dict], lista):
    """→ (resueltas [(producto, cantidad, precio)], problemas [str])."""
    hoy = date.today()
    ok, problemas = [], []
    for ln in lineas:
        nombre = ln.get("producto", "")
        cant = _dec(ln.get("cantidad"), f"Cantidad de {nombre}")
        if cant <= 0:
            problemas.append(f"cantidad de «{nombre}»")
            continue
        prod = _producto(empresa, nombre)
        if prod is None:
            problemas.append(f"producto «{nombre}» no encontrado o ambiguo")
            continue
        precio = ln.get("precio_unitario")
        if _vacio(precio) and lista is not None:
            dp = (
                DetallePrecio.objects.filter(
                    id_lista=lista, id_producto=prod, activo=True
                )
                .filter(Q(vigente_desde__isnull=True) | Q(vigente_desde__lte=hoy))
                .filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=hoy))
                .first()
            )
            precio = dp.precio if dp else None
        if _vacio(precio):
            problemas.append(
                f"precio de «{prod.nombre_producto}» (no está en la lista del cliente)"
            )
            continue
        ok.append((prod, cant, _dec(precio, f"Precio de {nombre}")))
    return ok, problemas


# ── contacto / CRM ───────────────────────────────────────────────────────────


def contacto(ctx: Ctx) -> Resultado:
    p = ctx.payload
    _exigir(p, ["nombre", "telefono", "ubicacion"])
    tel = _digitos(p["telefono"])
    if not 7 <= len(tel) <= 15:
        raise HandlerError("Teléfono inválido (7 a 15 dígitos).", faltan=["telefono"])
    gps = _gps(p["ubicacion"])
    existente = next(
        (
            c
            for c in Contacto.objects.filter(id_empresa=ctx.empresa, activo=True)
            if _digitos(c.telefono) == tel
        ),
        None,
    )
    if existente:
        c, creado = existente, False
        for k, v in {"email": p.get("email") or c.email, **gps}.items():
            setattr(c, k, v)
        c.save()
    else:
        c, creado = (
            Contacto.objects.create(
                id_empresa=ctx.empresa,
                nombre=p["nombre"].strip(),
                telefono=p["telefono"].strip(),
                email=p.get("email") or "",
                **gps,
            ),
            True,
        )

    res = {"contacto_id": str(c.id_contacto), "creado": creado}
    pipeline = Pipeline.objects.filter(
        id_empresa=ctx.empresa, activo=True, es_predeterminado=True
    ).first()
    etapa = (
        pipeline
        and Etapa.objects.filter(
            pipeline=pipeline, activo=True, tipo=Etapa.Tipo.ABIERTA
        )
        .order_by("orden")
        .first()
    )
    if pipeline and etapa:
        lead = Lead.objects.filter(
            id_empresa=ctx.empresa, contacto=c, activo=True
        ).first()
        if lead is None:
            lead = Lead.objects.create(
                id_empresa=ctx.empresa,
                nombre=c.nombre,
                email=c.email,
                telefono=c.telefono,
                mensaje=p.get("notas") or "",
                fuente=Lead.Fuente.MANUAL,
                pipeline=pipeline,
                etapa=etapa,
                propietario=ctx.usuario,
                contacto=c,
            )
        res["lead_id"] = str(lead.id_lead)
    else:
        res["aviso"] = (
            "La empresa no tiene un pipeline CRM predeterminado; se creó solo el contacto."
        )
    return Resultado(resultado=res)


# ── cotización / pedido ──────────────────────────────────────────────────────


def _moneda(lista, empresa):
    return lista.id_moneda if lista is not None else empresa.id_moneda_base


def cotizacion(ctx: Ctx) -> Resultado:
    p = ctx.payload
    _exigir(p, ["cliente"])
    cliente = _cliente_para(ctx.empresa, p["cliente"])
    lista = _lista_de(cliente, ctx.empresa)
    ok, problemas = _resolver_lineas(ctx.empresa, p.get("lineas") or [], lista)
    if not ok:
        raise HandlerError(
            "No pude armar la cotización: "
            + ("; ".join(problemas) or "indica al menos un producto")
            + ".",
            faltan=["lineas"],
        )
    hoy = date.today()
    cot = Cotizacion.objects.create(
        id_empresa=ctx.empresa,
        id_cliente=cliente,
        numero_cotizacion=siguiente_numero(ctx.empresa, "COTIZACION"),
        fecha_cotizacion=hoy,
        fecha_vencimiento=hoy + timedelta(days=15),
        id_moneda=_moneda(lista, ctx.empresa),
        observaciones=p.get("observaciones") or None,
        documento_json={
            "origen": "bot",
            "vendedor": str(ctx.usuario.pk),
            "lista": lista.codigo if lista else None,
        },
    )
    total = Decimal(0)
    for prod, cant, precio in ok:
        sub = cant * precio
        total += sub
        DetalleCotizacion.objects.create(
            id_cotizacion=cot,
            id_producto=prod,
            cantidad=cant,
            precio_unitario=precio,
            subtotal=sub,
        )
    cot.monto_total = total
    cot.save(update_fields=["monto_total"])
    return Resultado(
        resultado={
            "cotizacion_id": str(cot.id_cotizacion),
            "numero": cot.numero_cotizacion,
            "cliente_id": str(cliente.id_cliente),
            "total": str(total),
            "cliente_provisional": bool(
                (cliente.documento_json or {}).get("provisional")
            ),
        },
        incompleto=problemas,
        estado="INCOMPLETO" if problemas else "PROCESADO",
    )


_REQ_PEDIDO = ["cliente", "lineas", "rif", "email", "direccion_fiscal", "ubicacion"]


def pedido(ctx: Ctx) -> Resultado:
    p = ctx.payload
    _exigir(p, _REQ_PEDIDO)
    if not (p.get("direccion_entrega") or p.get("entrega_igual_fiscal")):
        raise HandlerError(
            "Indica la dirección de entrega o que es la misma fiscal.",
            faltan=["direccion_entrega"],
        )
    rif = _normalizar_rif(p["rif"])
    try:
        validar_rif(rif)
    except (
        ValidationError
    ) as e:  # defensa en profundidad: mismo validador que el modelo
        raise HandlerError(e.messages[0], faltan=["rif"]) from e
    gps = _gps(p["ubicacion"])

    cliente = _cliente_para(ctx.empresa, p["cliente"], rif)
    lista = _lista_de(cliente, ctx.empresa)
    ok, problemas = _resolver_lineas(ctx.empresa, p["lineas"], lista)
    if problemas or not ok:
        raise HandlerError(
            "No pude armar el pedido: "
            + "; ".join(problemas or ["sin productos"])
            + ".",
            faltan=["lineas"],
        )

    # La ficha del cliente se completa al confirmar el pedido.
    cliente.rif = rif
    cliente.email = p["email"].strip()
    if p.get("telefono"):
        cliente.telefono = p["telefono"].strip()
    cliente.direccion = p["direccion_fiscal"].strip()
    cliente.documento_json = {**(cliente.documento_json or {}), "provisional": False}
    cliente.save()
    if cliente.contacto_id:
        c = cliente.contacto
        c.rif, c.email, c.direccion_fiscal = rif, cliente.email, cliente.direccion
        for k, v in gps.items():
            setattr(c, k, v)
        c.save()

    def _dir(tipo, texto, con_gps):
        d, _ = DireccionCliente.objects.get_or_create(
            id_empresa=ctx.empresa,
            id_cliente=cliente,
            tipo_direccion=tipo,
            defaults={
                "direccion_completa": texto,
                "ciudad": "N/D",
                "estado_provincia": "N/D",
            },
        )
        d.direccion_completa = texto
        if con_gps:
            for k, v in gps.items():
                setattr(d, k, v)
        d.save()
        return d

    igual = bool(p.get("entrega_igual_fiscal")) or not p.get("direccion_entrega")
    fiscal = _dir("FISCAL", p["direccion_fiscal"].strip(), con_gps=igual)
    entrega = (
        fiscal
        if igual
        else _dir("ENTREGA", p["direccion_entrega"].strip(), con_gps=True)
    )

    entrega_est = None
    if p.get("fecha_entrega"):
        try:
            entrega_est = date.fromisoformat(p["fecha_entrega"])
        except ValueError as e:
            raise HandlerError(
                "Fecha de entrega inválida (usa AAAA-MM-DD).", faltan=["fecha_entrega"]
            ) from e
    ped = Pedido.objects.create(
        id_empresa=ctx.empresa,
        id_cliente=cliente,
        id_vendedor=ctx.usuario,
        numero_pedido=siguiente_numero(ctx.empresa, "PEDIDO"),
        fecha_pedido=date.today(),
        fecha_cierre_estimada=entrega_est,
        observaciones=p.get("observaciones") or None,
        documento_json={
            "origen": "bot",
            "lista": lista.codigo if lista else None,
            "direccion_entrega_id": str(entrega.id_direccion),
        },
    )
    total = Decimal(0)
    for prod, cant, precio in ok:
        sub = cant * precio
        total += sub
        DetallePedido.objects.create(
            id_pedido=ped,
            id_producto=prod,
            cantidad=cant,
            precio_unitario=precio,
            subtotal=sub,
        )
    return Resultado(
        resultado={
            "pedido_id": str(ped.id_pedido),
            "numero": ped.numero_pedido,
            "cliente_id": str(cliente.id_cliente),
            "total": str(total),
        }
    )


# ── pagos ────────────────────────────────────────────────────────────────────


def _pago_base(ctx: Ctx, requeridos: list[str]) -> tuple[list[str], dict]:
    p = ctx.payload
    incompleto = [c for c in requeridos if _vacio(p.get(c))]
    if p.get("monto") is not None:
        if _dec(p["monto"], "Monto") <= 0:
            raise HandlerError("El monto debe ser mayor que cero.", faltan=["monto"])
    return incompleto, {}


def pago(ctx: Ctx) -> Resultado:
    """Pago de cliente. El cliente se identifica por nombre, RIF *o* referencia de pedido (basta uno)."""
    p = ctx.payload
    incompleto, res = _pago_base(ctx, ["monto", "moneda", "referencia"])
    cliente = None
    pedido_ref = (p.get("pedido_ref") or "").strip()
    if pedido_ref:
        ped = (
            Pedido.objects.filter(
                id_empresa=ctx.empresa, numero_pedido__iexact=pedido_ref
            )
            .select_related("id_cliente")
            .first()
        )
        if ped:
            res["pedido_id"], cliente = str(ped.id_pedido), ped.id_cliente
    cliente = cliente or _buscar_cliente(ctx.empresa, p.get("cliente"), p.get("rif"))
    if cliente:
        res["cliente_id"] = str(cliente.id_cliente)
    elif _vacio(p.get("cliente")) and _vacio(p.get("rif")) and not pedido_ref:
        incompleto.append("cliente (nombre, RIF o pedido)")
    else:
        res["aviso"] = (
            "Cliente no encontrado en Omni; se resolverá al confirmar en Odoo."
        )
    return Resultado(
        resultado=res,
        incompleto=incompleto,
        estado="INCOMPLETO" if incompleto else "BORRADOR",
    )


def pago_proveedor(ctx: Ctx) -> Resultado:
    from apps.proveedores.models import Proveedor

    p = ctx.payload
    incompleto, res = _pago_base(ctx, ["proveedor", "monto", "moneda"])
    if p.get("proveedor"):
        prov = (
            Proveedor.objects.filter(id_empresa=ctx.empresa)
            .filter(
                Q(razon_social__iexact=p["proveedor"].strip())
                | Q(nombre_comercial__iexact=p["proveedor"].strip())
            )
            .first()
        )
        if prov:
            res["proveedor_id"] = str(prov.pk)
        else:
            res["aviso"] = (
                "Proveedor no encontrado en Omni; se resolverá al confirmar en Odoo."
            )
    return Resultado(
        resultado=res,
        incompleto=incompleto,
        estado="INCOMPLETO" if incompleto else "BORRADOR",
    )


# ── evento ───────────────────────────────────────────────────────────────────

_REQ_EVENTO = ["cliente", "ubicacion", "fecha", "hora_inicio", "hora_fin"]


def evento(ctx: Ctx) -> Resultado:
    p = ctx.payload
    _exigir(p, _REQ_EVENTO)
    if p.get("promotoras") is None or p.get("igloos") is None:
        raise HandlerError(
            "Indica cuántas promotoras e igloos necesita (0 si ninguno).",
            faltan=["promotoras", "igloos"],
        )
    try:
        cal = activ.calendario_predeterminado(ctx.empresa)
    except activ.ActivacionError as e:
        raise HandlerError(str(e)) from e
    tz = ZoneInfo(cal.zona_horaria)
    try:
        inicio = datetime.fromisoformat(f"{p['fecha']}T{p['hora_inicio']}:00").replace(
            tzinfo=tz
        )
        fin = datetime.fromisoformat(f"{p['fecha']}T{p['hora_fin']}:00").replace(
            tzinfo=tz
        )
    except ValueError as e:
        raise HandlerError(
            "Fecha u hora inválida (usa AAAA-MM-DD y HH:MM).", faltan=["fecha"]
        ) from e
    usos = {"promotoras": int(p["promotoras"]), "igloos": int(p["igloos"])}
    # Solo se exigen los recursos que el calendario administra; el resto se ignora si es 0.
    existentes = set(cal.recursos.filter(activo=True).values_list("codigo", flat=True))
    usos = {k: v for k, v in usos.items() if v > 0 or k in existentes}
    try:
        ev = activ.crear_evento(
            empresa=ctx.empresa,
            calendario=cal,
            cliente=_buscar_cliente(ctx.empresa, p["cliente"]),
            cliente_nombre=p["cliente"].strip(),
            vendedor=ctx.usuario,
            vendedor_nombre=(
                p.get("vendedor") or ctx.usuario.get_full_name() or ctx.usuario.username
            ),
            ubicacion=p["ubicacion"].strip(),
            inicio=inicio,
            fin=fin,
            usos=usos,
            materiales=p.get("materiales") or [],
            notas=p.get("notas") or "",
            origen=activ.EventoActivacion.Origen.BOT,
        )
    except activ.CapacidadExcedida as e:
        raise HandlerError(f"{e} Cambia el horario o los recursos.", status=409) from e
    except activ.ActivacionError as e:
        raise HandlerError(str(e)) from e
    return Resultado(
        resultado={"evento_id": str(ev.id_evento), "calendario": cal.nombre}
    )


HANDLERS = {
    "contacto": contacto,
    "cotizacion": cotizacion,
    "pedido": pedido,
    "pago": pago,
    "pago_proveedor": pago_proveedor,
    "evento": evento,
}
