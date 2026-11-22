import csv
import hashlib
import io
import os
import re
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.core.models import Empresa, Usuarios
from apps.core.uuid import uuid7
from apps.finanzas.models import CuentaBancariaEmpresa, Pago
from apps.nomina.models import Nomina, ProcesoNomina
from apps.proveedores.models import CuentaBancariaProveedor, Proveedor
from apps.tesoreria.models import MovimientoBancario

from .models import DetalleLotePagoBancario, LotePagoBancario


class BancaElectronicaError(Exception):
    """Error de dominio para operaciones bancarias VE y lotes de pago."""


SUDEBAN_BANCOS_VE: dict[str, str] = {
    "0102": "Banco de Venezuela",
    "0104": "Venezolano de Crédito",
    "0105": "Mercantil",
    "0108": "BBVA Provincial",
    "0114": "Bancaribe",
    "0115": "Banco Exterior",
    "0128": "Banco Caroní",
    "0134": "Banesco",
    "0137": "Sofitasa",
    "0138": "Banco Plaza",
    "0151": "BFC Fondo Común",
    "0156": "100% Banco",
    "0157": "DelSur",
    "0163": "Banco del Tesoro",
    "0166": "Banco Agrícola de Venezuela",
    "0168": "Bancrecer",
    "0169": "R4 / Mi Banco",
    "0171": "Banco Activo",
    "0172": "Bancamiga",
    "0174": "Banplus",
    "0175": "Banco Digital de los Trabajadores",
    "0177": "BANFANB",
    "0191": "BNC Banco Nacional de Crédito",
}

FORMATOS_TXT = {"BANESCO_TXT", "MERCANTIL_TXT", "BDV_TXT"}
FORMATOS_VALIDOS = FORMATOS_TXT | {"GENERICO_CSV"}
ESTADOS_LOTE_ACTIVOS = ("GENERADO", "ENVIADO", "PROCESADO")

TRANSICIONES_ESTADO: dict[str, set[str]] = {
    "BORRADOR": {"GENERADO", "ANULADO"},
    "GENERADO": {"ENVIADO", "ANULADO"},
    "ENVIADO": {"PROCESADO"},
    "PROCESADO": set(),
    "ANULADO": set(),
}

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def validar_cuenta_bancaria_ve(numero_cuenta: str) -> dict:
    """Valida una cuenta bancaria venezolana de 20 dígitos según prefijos SUDEBAN."""
    raw = "" if numero_cuenta is None else str(numero_cuenta)
    normalizado = re.sub(r"[\s\-]", "", raw)
    errores: list[str] = []

    if not normalizado:
        errores.append("El número de cuenta no puede estar vacío.")
        return {
            "valida": False,
            "numero_normalizado": "",
            "codigo_banco": None,
            "banco_nombre": None,
            "errores": errores,
        }

    if not normalizado.isdigit():
        errores.append("El número de cuenta solo debe contener dígitos numéricos.")

    if len(normalizado) != 20:
        errores.append("La cuenta bancaria venezolana debe tener exactamente 20 dígitos.")

    codigo_banco = normalizado[:4] if len(normalizado) >= 4 and normalizado[:4].isdigit() else None
    banco_nombre = SUDEBAN_BANCOS_VE.get(codigo_banco) if codigo_banco else None

    if codigo_banco is not None and banco_nombre is None:
        errores.append(f"El código bancario SUDEBAN '{codigo_banco}' no es válido.")

    return {
        "valida": len(errores) == 0,
        "numero_normalizado": normalizado,
        "codigo_banco": codigo_banco,
        "banco_nombre": banco_nombre,
        "errores": errores,
    }


def validar_referencia_bancaria(
    *,
    empresa: Empresa | UUID | str,
    cuenta_bancaria: CuentaBancariaEmpresa | UUID | str | None,
    referencia: str,
    excluir_pago_id: UUID | str | None = None,
) -> dict:
    """Detecta referencias bancarias duplicadas en pagos, extractos y lotes activos dentro del tenant."""
    ref_norm = ("" if referencia is None else str(referencia)).strip().upper()
    if not ref_norm:
        raise BancaElectronicaError("La referencia bancaria es obligatoria.")

    empresa_uuid = empresa.pk if isinstance(empresa, Empresa) else UUID(str(empresa))
    cuenta_uuid = (
        cuenta_bancaria.pk
        if isinstance(cuenta_bancaria, CuentaBancariaEmpresa)
        else (UUID(str(cuenta_bancaria)) if cuenta_bancaria is not None else None)
    )

    coincidencias: list[dict[str, str]] = []

    pagos_qs = Pago.objects.filter(id_empresa_id=empresa_uuid, referencia__iexact=ref_norm)
    if cuenta_uuid is not None:
        pagos_qs = pagos_qs.filter(Q(id_cuenta_bancaria_id=cuenta_uuid) | Q(banco_destino_id=cuenta_uuid))
    if excluir_pago_id is not None:
        pagos_qs = pagos_qs.exclude(pk=excluir_pago_id)
    for pago in pagos_qs.only("id_pago", "tipo_operacion", "referencia", "fecha_pago", "monto"):
        fecha_str = pago.fecha_pago.strftime("%Y-%m-%d") if pago.fecha_pago else ""
        coincidencias.append(
            {
                "origen": "finanzas.Pago",
                "id": str(pago.pk),
                "detalle": f"Pago {pago.tipo_operacion} ref={pago.referencia} fecha={fecha_str} monto={pago.monto}",
            }
        )

    movs_qs = MovimientoBancario.objects.filter(id_empresa_id=empresa_uuid, activo=True, referencia__iexact=ref_norm)
    if cuenta_uuid is not None:
        movs_qs = movs_qs.filter(id_cuenta_bancaria_id=cuenta_uuid)
    for mov in movs_qs.only("id", "tipo", "referencia", "fecha_mov", "monto"):
        coincidencias.append(
            {
                "origen": "tesoreria.MovimientoBancario",
                "id": str(mov.pk),
                "detalle": f"Extracto {mov.tipo} ref={mov.referencia} fecha={mov.fecha_mov} monto={mov.monto}",
            }
        )

    detalles_qs = (
        DetalleLotePagoBancario.objects.select_related("id_lote_pago")
        .filter(
            id_lote_pago__id_empresa_id=empresa_uuid,
            referencia_linea__iexact=ref_norm,
        )
        .exclude(id_lote_pago__estado="ANULADO")
    )
    if cuenta_uuid is not None:
        detalles_qs = detalles_qs.filter(id_lote_pago__id_cuenta_bancaria_id=cuenta_uuid)
    for det in detalles_qs:
        coincidencias.append(
            {
                "origen": "banca_electronica.DetalleLotePagoBancario",
                "id": str(det.pk),
                "detalle": (
                    f"Lote {det.id_lote_pago.referencia_lote} ({det.id_lote_pago.estado}) "
                    f"ref={det.referencia_linea} monto={det.monto}"
                ),
            }
        )

    return {
        "duplicada": len(coincidencias) > 0,
        "referencia_normalizada": ref_norm,
        "coincidencias": coincidencias,
    }


def _sanitizar_celda_csv(valor: object) -> str:
    """Neutraliza CSV formula injection prefijando comilla simple si inicia por carácter de fórmula."""
    texto = "" if valor is None else str(valor)
    texto = texto.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\x00", "")
    if texto and texto[0] in _FORMULA_PREFIXES:
        return f"'{texto}"
    return texto


def _sanitizar_txt(valor: object, max_len: int | None = None) -> str:
    """Limpia saltos de línea, tabuladores y nulos para registros TXT posicionales/delimitados."""
    texto = "" if valor is None else str(valor)
    limpio = re.sub(r"[\r\n\t\x00]+", " ", texto).strip()
    if max_len is not None:
        return limpio[:max_len]
    return limpio


def _nombre_archivo_seguro(referencia_lote: str, formato_banco: str) -> str:
    slug_ref = re.sub(r"[^A-Za-z0-9_\-]", "_", referencia_lote).strip("_") or "lote"
    ext = "csv" if formato_banco == "GENERICO_CSV" else "txt"
    return os.path.basename(f"lote_{formato_banco.lower()}_{slug_ref}.{ext}")


def _formatear_archivo_lote(
    *,
    formato_banco: str,
    tipo_lote: str,
    referencia_lote: str,
    fecha_valor: date,
    cuenta_origen: str,
    detalles: Sequence[dict],
    monto_total: Decimal,
) -> str:
    cuenta_origen_norm = re.sub(r"[\s\-]", "", cuenta_origen)
    monto_total_q = monto_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if formato_banco == "GENERICO_CSV":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(
            [
                "LOTE",
                "FECHA_VALOR",
                "TIPO_LOTE",
                "CUENTA_ORIGEN",
                "BENEFICIARIO",
                "IDENTIFICACION",
                "CUENTA_DESTINO",
                "BANCO_DESTINO",
                "MONTO",
                "REFERENCIA",
                "CONCEPTO",
            ]
        )
        for item in detalles:
            monto_str = str(item["monto"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            writer.writerow(
                [
                    _sanitizar_celda_csv(referencia_lote),
                    _sanitizar_celda_csv(fecha_valor.isoformat()),
                    _sanitizar_celda_csv(tipo_lote),
                    _sanitizar_celda_csv(cuenta_origen_norm),
                    _sanitizar_celda_csv(item["beneficiario_nombre"]),
                    _sanitizar_celda_csv(item["beneficiario_identificacion"]),
                    _sanitizar_celda_csv(item["cuenta_destino"]),
                    _sanitizar_celda_csv(item["banco_destino"]),
                    monto_str,
                    _sanitizar_celda_csv(item["referencia_linea"]),
                    _sanitizar_celda_csv(item["concepto"]),
                ]
            )
        return buf.getvalue()

    lineas: list[str] = []
    ref_limpia = _sanitizar_txt(referencia_lote, 60)
    cta_orig_limpia = _sanitizar_txt(cuenta_origen_norm, 50)
    total_reg = len(detalles)

    if formato_banco == "BANESCO_TXT":
        lineas.append(
            f"01|BANESCO|{ref_limpia}|{fecha_valor:%Y%m%d}|{cta_orig_limpia}|{total_reg:05d}|{monto_total_q}"
        )
        for idx, item in enumerate(detalles, start=1):
            monto_q = item["monto"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            lineas.append(
                "|".join(
                    [
                        "02",
                        f"{idx:05d}",
                        _sanitizar_txt(item["beneficiario_identificacion"], 40),
                        _sanitizar_txt(item["beneficiario_nombre"], 200),
                        _sanitizar_txt(item["cuenta_destino"], 50),
                        f"{monto_q}",
                        _sanitizar_txt(item["referencia_linea"], 60),
                        _sanitizar_txt(item["concepto"], 200),
                    ]
                )
            )
    elif formato_banco == "MERCANTIL_TXT":
        total_centimos = int((monto_total_q * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))
        lineas.append(
            f"1;MERCANTIL;{ref_limpia};{fecha_valor:%Y%m%d};{cta_orig_limpia};{total_reg:05d};{total_centimos:015d}"
        )
        for idx, item in enumerate(detalles, start=1):
            monto_q = item["monto"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            centimos = int((monto_q * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))
            lineas.append(
                ";".join(
                    [
                        "2",
                        f"{idx:05d}",
                        _sanitizar_txt(item["beneficiario_identificacion"], 40),
                        _sanitizar_txt(item["cuenta_destino"], 50),
                        f"{centimos:015d}",
                        _sanitizar_txt(item["beneficiario_nombre"], 200),
                        _sanitizar_txt(item["referencia_linea"], 60),
                        _sanitizar_txt(item["concepto"], 200),
                    ]
                )
            )
    elif formato_banco == "BDV_TXT":
        lineas.append(f"HBDV|{ref_limpia}|{fecha_valor:%d/%m/%Y}|{cta_orig_limpia}|{total_reg:05d}|{monto_total_q}")
        for idx, item in enumerate(detalles, start=1):
            monto_q = item["monto"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            lineas.append(
                "|".join(
                    [
                        "DBDV",
                        f"{idx:05d}",
                        _sanitizar_txt(item["beneficiario_identificacion"], 40),
                        _sanitizar_txt(item["beneficiario_nombre"], 200),
                        _sanitizar_txt(item["cuenta_destino"], 50),
                        f"{monto_q}",
                        _sanitizar_txt(item["referencia_linea"], 60),
                        _sanitizar_txt(item["concepto"], 200),
                    ]
                )
            )
    else:
        raise BancaElectronicaError(f"Formato bancario no soportado: {formato_banco}.")

    return "\n".join(lineas) + "\n"


def _validar_y_obtener_cuenta_origen(
    empresa: Empresa, cuenta_bancaria: CuentaBancariaEmpresa | UUID | str
) -> CuentaBancariaEmpresa:
    cuenta_pk = cuenta_bancaria.pk if isinstance(cuenta_bancaria, CuentaBancariaEmpresa) else cuenta_bancaria
    cuenta = CuentaBancariaEmpresa.objects.select_for_update().filter(pk=cuenta_pk, id_empresa=empresa).first()
    if cuenta is None:
        raise BancaElectronicaError("La cuenta bancaria origen no existe o no pertenece a la empresa.")
    if not cuenta.activo:
        raise BancaElectronicaError("La cuenta bancaria origen se encuentra inactiva.")
    return cuenta


def _resolver_referencia_lote(empresa: Empresa, prefijo: str, fecha_valor: date, referencia_lote: str | None) -> str:
    if referencia_lote is not None and str(referencia_lote).strip():
        ref = str(referencia_lote).strip()[:60]
        if LotePagoBancario.objects.filter(id_empresa=empresa, referencia_lote=ref).exists():
            raise BancaElectronicaError(f"Ya existe un lote de pago con referencia '{ref}' en la empresa.")
        return ref
    while True:
        # Los bits finales de UUIDv7 son aleatorios (los primeros 12 hex codifican timestamp).
        candidata = f"{prefijo}-{fecha_valor:%Y%m%d}-{uuid7().hex[-8:].upper()}"
        if not LotePagoBancario.objects.filter(id_empresa=empresa, referencia_lote=candidata).exists():
            return candidata


def _validar_cuenta_destino_por_formato(cuenta_raw: str, formato_banco: str, etiqueta: str) -> tuple[str, str]:
    limpia = (cuenta_raw or "").strip()
    if not limpia:
        raise BancaElectronicaError(f"Falta cuenta bancaria destino para {etiqueta}.")
    res_ve = validar_cuenta_bancaria_ve(limpia)
    if formato_banco in FORMATOS_TXT:
        if not res_ve["valida"]:
            raise BancaElectronicaError(
                f"Cuenta destino inválida para {etiqueta} en formato {formato_banco}: " + "; ".join(res_ve["errores"])
            )
        return res_ve["numero_normalizado"], res_ve["banco_nombre"] or ""
    return limpia, res_ve["banco_nombre"] or ""


def _resolver_proveedor_de_pago(pago: Pago, empresa: Empresa) -> Proveedor | None:
    if pago.id_contacto is not None:
        try:
            prov = pago.id_contacto.proveedor
        except ObjectDoesNotExist:
            prov = None
        if prov is not None and prov.id_empresa_id == empresa.pk:
            return prov

    if pago.id_cxp is not None and getattr(pago.id_cxp, "id_proveedor", None) is not None:
        prov = pago.id_cxp.id_proveedor
        if prov.id_empresa_id == empresa.pk:
            return prov

    asignaciones = (
        pago.asignaciones.filter(activo=True)
        .exclude(estado="REVERTIDA")
        .select_related(
            "id_cxp__id_proveedor",
            "id_factura_compra__id_proveedor",
            "id_factura_compra__id_orden_compra__id_proveedor",
        )
        .order_by("fecha_creacion")
    )
    for asig in asignaciones:
        if asig.id_cxp is not None and getattr(asig.id_cxp, "id_proveedor", None) is not None:
            prov = asig.id_cxp.id_proveedor
            if prov.id_empresa_id == empresa.pk:
                return prov
        if asig.id_factura_compra is not None:
            prov = getattr(asig.id_factura_compra, "id_proveedor", None)
            if prov is None and asig.id_factura_compra.id_orden_compra is not None:
                prov = getattr(asig.id_factura_compra.id_orden_compra, "id_proveedor", None)
            if prov is not None and prov.id_empresa_id == empresa.pk:
                return prov
    return None


def _crear_lote_con_reintento(
    *,
    empresa: Empresa,
    cuenta: CuentaBancariaEmpresa,
    tipo_lote: str,
    formato_banco: str,
    prefijo_ref: str,
    referencia_explicita: str | None,
    fecha_valor: date,
    detalles_data: list[dict],
    monto_total: Decimal,
    usuario: Usuarios | None,
    proceso_nomina: ProcesoNomina | None = None,
) -> LotePagoBancario:
    """Persiste ``LotePagoBancario`` y sus detalles protegiendo colisiones de ``referencia_lote``."""
    es_explicita = bool(referencia_explicita is not None and str(referencia_explicita).strip())
    max_intentos = 1 if es_explicita else 5

    for intento in range(max_intentos):
        ref_lote = _resolver_referencia_lote(
            empresa,
            prefijo_ref,
            fecha_valor,
            referencia_explicita if es_explicita else None,
        )
        contenido = _formatear_archivo_lote(
            formato_banco=formato_banco,
            tipo_lote=tipo_lote,
            referencia_lote=ref_lote,
            fecha_valor=fecha_valor,
            cuenta_origen=cuenta.numero_cuenta,
            detalles=detalles_data,
            monto_total=monto_total,
        )
        sha256_archivo = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
        nombre_archivo = _nombre_archivo_seguro(ref_lote, formato_banco)

        try:
            with transaction.atomic():
                lote = LotePagoBancario.objects.create(
                    id_empresa=empresa,
                    id_cuenta_bancaria=cuenta,
                    tipo_lote=tipo_lote,
                    formato_banco=formato_banco,
                    referencia_lote=ref_lote,
                    fecha_valor=fecha_valor,
                    estado="GENERADO",
                    id_proceso_nomina=proceso_nomina,
                    total_registros=len(detalles_data),
                    monto_total=monto_total,
                    contenido_archivo=contenido,
                    sha256_archivo=sha256_archivo,
                    nombre_archivo=nombre_archivo,
                    generado_por=usuario,
                )
                DetalleLotePagoBancario.objects.bulk_create(
                    [DetalleLotePagoBancario(id_lote_pago=lote, **item) for item in detalles_data]
                )
                return lote
        except IntegrityError as exc:
            if es_explicita:
                raise BancaElectronicaError(
                    f"Ya existe un lote de pago con referencia '{ref_lote}' en la empresa."
                ) from exc
            if intento == max_intentos - 1:
                raise BancaElectronicaError(
                    "No se pudo generar una referencia única para el lote tras varios reintentos."
                ) from exc

    raise BancaElectronicaError("No se pudo crear el lote de pago bancario.")


@transaction.atomic
def generar_lote_pagos_proveedores(
    *,
    empresa: Empresa,
    cuenta_bancaria: CuentaBancariaEmpresa | UUID | str,
    pagos_ids: Sequence[UUID | str],
    formato_banco: str,
    fecha_valor: date,
    usuario: Usuarios | None = None,
    referencia_lote: str | None = None,
    cuentas_destino_override: Mapping[str, str] | None = None,
) -> LotePagoBancario:
    """Genera un lote de pagos masivos a proveedores con bloqueo pesimista y SHA-256."""
    if formato_banco not in FORMATOS_VALIDOS:
        raise BancaElectronicaError(f"Formato de banco no válido: {formato_banco}.")

    ids_lista = [str(pid) for pid in pagos_ids]
    if not ids_lista:
        raise BancaElectronicaError("Debe seleccionar al menos un pago para generar el lote.")
    if len(set(ids_lista)) != len(ids_lista):
        raise BancaElectronicaError("La lista de pagos contiene identificadores duplicados.")

    cuenta = _validar_y_obtener_cuenta_origen(empresa, cuenta_bancaria)

    pagos_db = list(
        Pago.objects.select_for_update(of=("self",))
        .select_related("id_contacto", "id_cxp__id_proveedor")
        .filter(id_empresa=empresa, pk__in=ids_lista)
        .order_by("pk")
    )
    if len(pagos_db) != len(ids_lista):
        raise BancaElectronicaError("Uno o más pagos no existen o no pertenecen a la empresa.")

    detalle_activo = (
        DetalleLotePagoBancario.objects.select_related("id_lote_pago")
        .filter(id_pago_id__in=ids_lista, id_lote_pago__estado__in=ESTADOS_LOTE_ACTIVOS)
        .first()
    )
    if detalle_activo is not None:
        raise BancaElectronicaError(
            f"El pago {detalle_activo.id_pago_id} ya forma parte del lote activo "
            f"{detalle_activo.id_lote_pago.referencia_lote}."
        )

    pagos_por_id = {str(p.pk): p for p in pagos_db}
    overrides = {str(k): str(v) for k, v in (cuentas_destino_override or {}).items()}

    detalles_data: list[dict] = []
    monto_total = Decimal("0.00")

    for pid in ids_lista:
        pago = pagos_por_id[pid]
        if pago.tipo_operacion != "EGRESO":
            raise BancaElectronicaError(
                f"El pago {pago.pk} es de tipo '{pago.tipo_operacion}'; solo se permiten pagos EGRESO."
            )
        monto_q = Decimal(pago.monto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if monto_q <= Decimal("0.00"):
            raise BancaElectronicaError(f"El pago {pago.pk} debe tener un monto mayor a cero.")

        proveedor = _resolver_proveedor_de_pago(pago, empresa)
        if proveedor is not None:
            benef_nombre = proveedor.razon_social or proveedor.nombre_comercial or "Proveedor"
            benef_id = proveedor.rif or "N/D"
        elif pago.id_contacto is not None:
            benef_nombre = (
                pago.id_contacto.nombre_completo
                or pago.id_contacto.nombre_comercial
                or pago.id_contacto.nombre
                or "Beneficiario"
            )
            benef_id = pago.id_contacto.rif or pago.id_contacto.cedula or "N/D"
        else:
            benef_nombre = f"Beneficiario {str(pago.pk)[:8]}"
            benef_id = "N/D"

        banco_destino = ""
        cuenta_raw = overrides.get(pid, "").strip()
        if not cuenta_raw and proveedor is not None:
            cta_prov = (
                CuentaBancariaProveedor.objects.filter(id_proveedor=proveedor, activo=True)
                .order_by("-es_cuenta_principal", "fecha_creacion")
                .first()
            )
            if cta_prov is not None:
                cuenta_raw = cta_prov.numero_cuenta
                banco_destino = cta_prov.nombre_banco

        if not cuenta_raw:
            raise BancaElectronicaError(
                f"El pago {pago.pk} ({benef_nombre}) no tiene cuenta bancaria destino asociada."
            )

        cuenta_destino, banco_detectado = _validar_cuenta_destino_por_formato(
            cuenta_raw, formato_banco, f"pago {pago.pk}"
        )
        if not banco_destino:
            banco_destino = banco_detectado

        ref_linea = (pago.referencia or f"PAG-{str(pago.pk)[:8]}").strip()[:60]
        concepto = (pago.observaciones or f"Pago a {benef_nombre}").strip()[:200]

        detalles_data.append(
            {
                "id_pago": pago,
                "id_nomina": None,
                "beneficiario_nombre": benef_nombre[:200],
                "beneficiario_identificacion": benef_id[:40],
                "cuenta_destino": cuenta_destino[:50],
                "banco_destino": banco_destino[:100],
                "monto": monto_q,
                "referencia_linea": ref_linea,
                "concepto": concepto,
            }
        )
        monto_total += monto_q

    return _crear_lote_con_reintento(
        empresa=empresa,
        cuenta=cuenta,
        tipo_lote="PROVEEDORES",
        formato_banco=formato_banco,
        prefijo_ref="LOTE-PROV",
        referencia_explicita=referencia_lote,
        fecha_valor=fecha_valor,
        detalles_data=detalles_data,
        monto_total=monto_total,
        usuario=usuario,
    )


@transaction.atomic
def generar_lote_pagos_nomina(
    *,
    empresa: Empresa,
    cuenta_bancaria: CuentaBancariaEmpresa | UUID | str,
    proceso_nomina: ProcesoNomina | UUID | str,
    formato_banco: str,
    fecha_valor: date,
    usuario: Usuarios | None = None,
    cuentas_empleados: Mapping[str, str] | None = None,
    referencia_lote: str | None = None,
) -> LotePagoBancario:
    """Genera un lote bancario de nómina para un ``ProcesoNomina`` completado o aprobado."""
    if formato_banco not in FORMATOS_VALIDOS:
        raise BancaElectronicaError(f"Formato de banco no válido: {formato_banco}.")

    cuenta = _validar_y_obtener_cuenta_origen(empresa, cuenta_bancaria)

    proc_pk = proceso_nomina.pk if isinstance(proceso_nomina, ProcesoNomina) else proceso_nomina
    proceso = ProcesoNomina.objects.select_for_update().filter(pk=proc_pk, id_empresa=empresa).first()
    if proceso is None:
        raise BancaElectronicaError("El proceso de nómina no existe o no pertenece a la empresa.")
    if proceso.estado not in ("COMPLETADO", "APROBADO"):
        raise BancaElectronicaError(
            f"El proceso de nómina debe estar en estado COMPLETADO o APROBADO (actual: {proceso.estado})."
        )

    lote_activo = LotePagoBancario.objects.filter(
        id_empresa=empresa,
        id_proceso_nomina=proceso,
        estado__in=ESTADOS_LOTE_ACTIVOS,
    ).first()
    if lote_activo is not None:
        raise BancaElectronicaError(
            f"Ya existe un lote activo ({lote_activo.referencia_lote}) para este proceso de nómina."
        )

    nominas = list(
        Nomina.objects.select_for_update(of=("self",))
        .select_related("id_empleado")
        .filter(id_proceso_nomina=proceso, total_neto__gt=0)
        .order_by("id_empleado__cedula", "pk")
    )
    if not nominas:
        raise BancaElectronicaError("El proceso de nómina no tiene nóminas con neto a pagar mayor a cero.")

    cuentas_map = {str(k): str(v) for k, v in (cuentas_empleados or {}).items()}
    detalles_data: list[dict] = []
    monto_total = Decimal("0.00")

    for nomina in nominas:
        emp = nomina.id_empleado
        monto_q = Decimal(nomina.total_neto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if monto_q <= Decimal("0.00"):
            continue

        cuenta_raw = cuentas_map.get(str(emp.pk), "").strip() or cuentas_map.get(str(nomina.pk), "").strip()
        if not cuenta_raw and isinstance(emp.documento_json, dict):
            cuenta_raw = str(
                emp.documento_json.get("numero_cuenta") or emp.documento_json.get("cuenta_bancaria") or ""
            ).strip()

        if not cuenta_raw:
            raise BancaElectronicaError(
                f"El empleado {emp.nombre} {emp.apellido} ({emp.cedula}) no tiene cuenta bancaria configurada."
            )

        cuenta_destino, banco_detectado = _validar_cuenta_destino_por_formato(
            cuenta_raw, formato_banco, f"empleado {emp.nombre} {emp.apellido}"
        )
        benef_nombre = f"{emp.nombre} {emp.apellido}".strip() or f"Empleado {emp.cedula}"
        ref_linea = f"NOM-{proceso.numero_proceso[:20]}-{emp.cedula[:20]}"[:60]
        concepto = f"Pago nómina {proceso.numero_proceso}"[:200]

        detalles_data.append(
            {
                "id_pago": None,
                "id_nomina": nomina,
                "beneficiario_nombre": benef_nombre[:200],
                "beneficiario_identificacion": str(emp.cedula)[:40],
                "cuenta_destino": cuenta_destino[:50],
                "banco_destino": banco_detectado[:100],
                "monto": monto_q,
                "referencia_linea": ref_linea,
                "concepto": concepto,
            }
        )
        monto_total += monto_q

    if not detalles_data:
        raise BancaElectronicaError("No se generaron líneas válidas para el lote de nómina.")

    return _crear_lote_con_reintento(
        empresa=empresa,
        cuenta=cuenta,
        tipo_lote="NOMINA",
        formato_banco=formato_banco,
        prefijo_ref="LOTE-NOM",
        referencia_explicita=referencia_lote,
        fecha_valor=fecha_valor,
        detalles_data=detalles_data,
        monto_total=monto_total,
        usuario=usuario,
        proceso_nomina=proceso,
    )


@transaction.atomic
def cambiar_estado_lote(
    lote: LotePagoBancario | UUID | str,
    nuevo_estado: str,
    usuario: Usuarios | None = None,
) -> LotePagoBancario:
    """Ejecuta transición estricta de estado sobre ``LotePagoBancario`` bajo lock."""
    lote_pk = lote.pk if isinstance(lote, LotePagoBancario) else lote
    lote_db = LotePagoBancario.objects.select_for_update().filter(pk=lote_pk).first()
    if lote_db is None:
        raise BancaElectronicaError("El lote de pago bancario no existe.")

    estados_validos = {codigo for codigo, _ in LotePagoBancario.ESTADOS}
    if nuevo_estado not in estados_validos:
        raise BancaElectronicaError(f"Estado de lote inválido: {nuevo_estado}.")

    permitidos = TRANSICIONES_ESTADO.get(lote_db.estado, set())
    if nuevo_estado not in permitidos:
        raise BancaElectronicaError(f"Transición de estado no permitida: '{lote_db.estado}' -> '{nuevo_estado}'.")

    lote_db.estado = nuevo_estado
    lote_db.save(update_fields=["estado", "fecha_actualizacion"])
    if isinstance(lote, LotePagoBancario):
        lote.estado = lote_db.estado
        lote.fecha_actualizacion = lote_db.fecha_actualizacion
    return lote_db
