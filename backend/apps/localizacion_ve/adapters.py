"""
Adaptadores VE de los puertos de localización (ADR-007 / GAP-2, strangler fig).

Implementa los 6 puertos definidos en ``apps.localizacion.ports`` para Venezuela:
  - Capa legal: ``MotorImpuestosVE``, ``GeneradorDocumentoLegalVE``,
    ``CalculadoraNominaVE``, ``LibroLegalVE``.
  - Capa de mercado: ``ProveedorTasasVE``, ``MetodosPagoLocalesVE``.

Los imports hacia ``apps.fiscal``, ``apps.nomina``, ``apps.finanzas`` y
``apps.localizacion_ve.validators`` son perezosos (dentro de los métodos) para
evitar ciclos durante el arranque de Django.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.localizacion.ports import (
    CalculadoraNomina,
    GeneradorDocumentoLegal,
    LibroLegal,
    MetodosPagoLocales,
    MotorImpuestos,
    ProveedorTasas,
)

_BOLIVAR_CODIGOS: frozenset[str] = frozenset({"VES", "BS", "VEF", "VEB"})


def _get_campo(obj: Any, *campos: str) -> Any:
    """Devuelve el primer valor no-None encontrado en dict u objeto."""
    if isinstance(obj, dict):
        for campo in campos:
            if campo in obj and obj[campo] is not None:
                return obj[campo]
        return None
    for campo in campos:
        val = getattr(obj, campo, None)
        if val is not None:
            return val
    return None


def _get_texto(obj: Any, *campos: str) -> str:
    """Devuelve el primer string no vacío encontrado en dict u objeto."""
    if isinstance(obj, dict):
        for campo in campos:
            val = obj.get(campo)
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""
    for campo in campos:
        val = getattr(obj, campo, None)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _a_decimal(valor: Any, *, campo: str) -> Decimal:
    """Convierte ``valor`` a ``Decimal`` finito (R-CODE-4), rechazando booleanos/NaN."""
    if isinstance(valor, bool):
        raise ValueError(f"El campo '{campo}' no puede ser booleano.")
    try:
        dec = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Valor numérico inválido en '{campo}': {valor!r}") from exc
    if not dec.is_finite():
        raise ValueError(f"El campo '{campo}' debe ser un número finito.")
    return dec


def _empresa_pk(empresa: Any) -> Any:
    pk = getattr(empresa, "id_empresa", None)
    if pk is not None:
        return pk
    return getattr(empresa, "pk", None)


def _validar_pertenencia_empresa(documento: Any, empresa: Any) -> None:
    """Garantiza aislamiento multi-tenant (R-CODE-1) al emitir documentos legales."""
    emp_pk = _empresa_pk(empresa)
    raw = _get_campo(documento, "id_empresa_id", "empresa_id", "id_empresa", "empresa")
    if raw is None:
        return
    raw_pk = _empresa_pk(raw)
    if emp_pk is not None:
        doc_id = raw_pk if raw_pk is not None else raw
        if str(doc_id) != str(emp_pk):
            raise PermissionError("El documento no pertenece a la empresa indicada.")
        return
    if raw is not empresa:
        raise PermissionError("El documento no pertenece a la empresa indicada.")


def _inferir_tipo_documento(documento: Any) -> str:
    explicit = _get_texto(documento, "tipo_documento")
    if explicit:
        return explicit.upper()
    cls_name = type(documento).__name__
    if cls_name == "FacturaFiscal" or _get_campo(documento, "numero_factura") is not None:
        return "FACTURA_FISCAL"
    if cls_name == "NotaCreditoFiscal" or _get_campo(documento, "id_nota_credito_fiscal") is not None:
        return "NOTA_CREDITO_FISCAL"
    if cls_name == "NotaCreditoVenta" or _get_campo(documento, "id_nota_credito", "numero_nota_credito") is not None:
        return "NOTA_CREDITO_VENTA"
    return "DOCUMENTO_FISCAL"


def _entero_estricto(valor: Any, campo: str) -> int:
    if isinstance(valor, bool):
        raise ValueError(f"'{campo}' no puede ser booleano.")
    try:
        return int(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valor inválido para '{campo}': {valor!r}") from exc


def _rango_mes(anio: int, mes: int) -> tuple[date, date]:
    if anio < 1900 or anio > 2100 or mes < 1 or mes > 12:
        raise ValueError(f"Período fuera de rango válido: año={anio!r}, mes={mes!r}.")
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo_dia)


def _a_fecha(valor: Any, campo: str) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            return date.fromisoformat(valor.strip())
        except ValueError as exc:
            raise ValueError(f"Fecha inválida para '{campo}': {valor!r}") from exc
    raise ValueError(f"Tipo de fecha inválido para '{campo}': {valor!r}")


def _resolver_rango_periodo(periodo: Any) -> tuple[date, date]:
    """Normaliza múltiples representaciones de período a ``(fecha_inicio, fecha_fin)``."""
    if periodo is None:
        raise ValueError("El parámetro 'periodo' es requerido.")

    if isinstance(periodo, str):
        from apps.fiscal.libros_seniat import _periodo_a_rango

        return _periodo_a_rango(periodo.strip())

    if isinstance(periodo, date):
        return _rango_mes(periodo.year, periodo.month)

    if isinstance(periodo, (tuple, list)):
        if len(periodo) != 2:
            raise ValueError(f"Tupla/lista de período debe tener exactamente 2 elementos, recibido: {periodo!r}")
        a, b = periodo
        if isinstance(a, date) and isinstance(b, date):
            inicio = a.date() if isinstance(a, datetime) else a
            fin = b.date() if isinstance(b, datetime) else b
            if inicio > fin:
                raise ValueError("La fecha de inicio del período no puede ser mayor que la fecha de fin.")
            return inicio, fin
        num_a = _entero_estricto(a, "periodo[0]")
        num_b = _entero_estricto(b, "periodo[1]")
        if 1 <= num_a <= 12 and 1900 <= num_b <= 2100:
            return _rango_mes(num_b, num_a)
        if 1900 <= num_a <= 2100 and 1 <= num_b <= 12:
            return _rango_mes(num_a, num_b)
        raise ValueError(f"Par (mes, anio) / (anio, mes) inválido: {periodo!r}")

    inicio_raw = _get_campo(periodo, "fecha_inicio", "desde")
    fin_raw = _get_campo(periodo, "fecha_fin", "hasta")
    if inicio_raw is not None and fin_raw is not None:
        inicio = _a_fecha(inicio_raw, "fecha_inicio")
        fin = _a_fecha(fin_raw, "fecha_fin")
        if inicio > fin:
            raise ValueError("La fecha de inicio del período no puede ser mayor que la fecha de fin.")
        return inicio, fin

    anio_raw = _get_campo(periodo, "año", "anio", "year")
    mes_raw = _get_campo(periodo, "mes", "month")
    if anio_raw is not None and mes_raw is not None:
        return _rango_mes(_entero_estricto(anio_raw, "anio"), _entero_estricto(mes_raw, "mes"))

    raise ValueError(f"Formato de período no soportado: {periodo!r}")


def _metadatos_metodo_pago_ve(
    metodo: Any,
    *,
    empresa_permite_igtf: bool,
    metodos_igtf: frozenset[str],
) -> dict[str, Any]:
    """Construye el descriptor VE de un ``MetodoPago`` (sin exponer ``documento_json``)."""
    monedas = list(metodo.monedas.all())
    monedas_codigos = sorted({str(m.codigo_iso).strip().upper() for m in monedas if getattr(m, "codigo_iso", None)})
    tiene_crypto = any(getattr(m, "tipo_moneda", "") == "crypto" for m in monedas)
    doc_json = metodo.documento_json if isinstance(metodo.documento_json, dict) else {}
    nombre_up = str(metodo.nombre_metodo or "").strip().upper()
    tipo_up = str(metodo.tipo_metodo or "OTRO").strip().upper()

    if isinstance(doc_json.get("es_divisa"), bool):
        es_divisa = doc_json["es_divisa"]
    elif isinstance(getattr(metodo, "es_divisa", None), bool):
        es_divisa = bool(getattr(metodo, "es_divisa"))
    elif monedas_codigos:
        es_divisa = any(codigo not in _BOLIVAR_CODIGOS for codigo in monedas_codigos)
    else:
        es_divisa = any(
            tok in nombre_up
            for tok in ("USD", "EUR", "USDT", "ZELLE", "BINANCE", "DIVISA", "CRYPTO", "CRIPTO", "DOLAR", "DÓLAR")
        )

    cat_override = doc_json.get("categoria_ve")
    if isinstance(cat_override, str) and cat_override.strip():
        categoria_ve = cat_override.strip().upper()
    elif "ZELLE" in nombre_up:
        categoria_ve = "ZELLE"
    elif "PAGO MOVIL" in nombre_up or "PAGO MÓVIL" in nombre_up or "PAGOMOVIL" in nombre_up:
        categoria_ve = "PAGO_MOVIL"
    elif tiene_crypto or any(tok in nombre_up for tok in ("USDT", "BINANCE", "CRYPTO", "CRIPTO", "PETRO")):
        categoria_ve = "CRYPTO"
    elif tipo_up == "TARJETA" or any(tok in nombre_up for tok in ("TARJETA", "PUNTO", "BIOPAGO")):
        categoria_ve = "TARJETA"
    elif tipo_up == "EFECTIVO" and es_divisa:
        categoria_ve = "DIVISA_EFECTIVO"
    elif tipo_up == "EFECTIVO":
        categoria_ve = "EFECTIVO_BS"
    elif tipo_up == "ELECTRONICO" and es_divisa:
        categoria_ve = "DIVISA_TRANSFERENCIA"
    elif tipo_up == "ELECTRONICO":
        categoria_ve = "TRANSFERENCIA_BS"
    else:
        categoria_ve = tipo_up

    if isinstance(doc_json.get("aplica_igtf"), bool):
        base_igtf = doc_json["aplica_igtf"]
    elif isinstance(getattr(metodo, "aplica_igtf", None), bool):
        base_igtf = bool(getattr(metodo, "aplica_igtf"))
    else:
        base_igtf = (categoria_ve in metodos_igtf) or (categoria_ve == "ZELLE") or es_divisa

    return {
        "id_metodo_pago": str(metodo.id_metodo_pago),
        "nombre_metodo": str(metodo.nombre_metodo),
        "tipo_metodo": tipo_up,
        "monedas": monedas_codigos,
        "es_divisa": es_divisa,
        "aplica_igtf": bool(empresa_permite_igtf and base_igtf),
        "categoria_ve": categoria_ve,
        "es_generico": bool(metodo.es_generico),
        "es_publico": bool(metodo.es_publico),
        "pais": "VE",
    }


# ── Capa legal (A) ────────────────────────────────────────────────────────────


class MotorImpuestosVE(MotorImpuestos):
    """Motor de impuestos venezolano: IVA + IGTF (delega en apps.fiscal)."""

    def calcular(self, *, subtotal: Decimal, empresa, contexto: dict | None = None) -> dict:
        from apps.fiscal.services import calcular_impuestos

        return calcular_impuestos(Decimal(str(subtotal)), empresa)


class GeneradorDocumentoLegalVE(GeneradorDocumentoLegal):
    """Emite la representación legal SENIAT de facturas y notas de crédito VE."""

    def emitir(self, *, documento, empresa) -> dict:
        if empresa is None:
            raise ValueError("La empresa es requerida para emitir un documento legal VE.")
        if documento is None:
            raise ValueError("El documento es requerido para emitir un documento legal VE.")

        _validar_pertenencia_empresa(documento, empresa)

        from apps.localizacion_ve.validators import normalizar_rif

        rif_emisor_raw = _get_texto(empresa, "identificador_fiscal", "rif")
        rif_emisor = normalizar_rif(rif_emisor_raw)

        cliente_obj = _get_campo(documento, "id_cliente", "cliente")
        rif_receptor_raw = _get_texto(documento, "rif_receptor", "rif_cliente")
        if not rif_receptor_raw and cliente_obj is not None:
            rif_receptor_raw = _get_texto(cliente_obj, "rif", "identificador_fiscal")

        tiene_campo_receptor = (
            cliente_obj is not None
            or hasattr(documento, "_meta")
            or (
                isinstance(documento, dict)
                and any(k in documento for k in ("rif_receptor", "rif_cliente", "id_cliente", "cliente"))
            )
        )
        if rif_receptor_raw:
            rif_receptor = normalizar_rif(rif_receptor_raw)
        elif tiene_campo_receptor:
            raise ValueError("El RIF del cliente/receptor es requerido para emitir un documento legal VE.")
        else:
            rif_receptor = ""

        tipo_documento = _inferir_tipo_documento(documento)
        numero_documento = _get_texto(
            documento,
            "numero_documento",
            "numero_factura",
            "numero_nota_credito",
            "numero",
        )
        numero_control = _get_texto(documento, "numero_control")
        if not numero_control:
            factura_origen = _get_campo(documento, "id_factura_origen")
            if factura_origen is not None:
                numero_control = _get_texto(factura_origen, "numero_control")

        fecha_raw = _get_campo(documento, "fecha_emision", "fecha")
        if isinstance(fecha_raw, datetime):
            fecha_emision = fecha_raw.date().isoformat()
        elif isinstance(fecha_raw, date):
            fecha_emision = fecha_raw.isoformat()
        else:
            fecha_emision = str(fecha_raw).strip() if fecha_raw is not None else ""

        moneda_raw = _get_campo(documento, "moneda", "id_moneda")
        if moneda_raw is None:
            moneda_raw = _get_campo(empresa, "id_moneda_base")
        if moneda_raw is not None and hasattr(moneda_raw, "codigo_iso"):
            moneda = str(moneda_raw.codigo_iso).strip().upper()
        else:
            moneda = str(moneda_raw).strip().upper() if moneda_raw is not None else ""

        iva_raw = _get_campo(documento, "iva", "monto_iva", "monto_impuesto")
        igtf_raw = _get_campo(documento, "igtf", "monto_igtf")
        exento_raw = _get_campo(documento, "exento", "monto_exento", "base_exenta")
        subtotal_raw = _get_campo(documento, "subtotal", "base_imponible", "monto_base")
        total_raw = _get_campo(documento, "total", "monto_total")

        iva = _a_decimal(iva_raw, campo="iva") if iva_raw is not None else Decimal("0")
        igtf = _a_decimal(igtf_raw, campo="igtf") if igtf_raw is not None else Decimal("0")
        exento = _a_decimal(exento_raw, campo="exento") if exento_raw is not None else Decimal("0")

        if subtotal_raw is not None:
            subtotal = _a_decimal(subtotal_raw, campo="subtotal")
        elif total_raw is not None:
            total_tmp = _a_decimal(total_raw, campo="total")
            subtotal = total_tmp - iva - igtf - exento
        else:
            subtotal = Decimal("0")

        if total_raw is not None:
            total = _a_decimal(total_raw, campo="total")
        else:
            total = subtotal + iva + igtf + exento

        return {
            "tipo_documento": tipo_documento,
            "numero_documento": numero_documento,
            "numero_control": numero_control,
            "fecha_emision": fecha_emision,
            "moneda": moneda,
            "rif_emisor": rif_emisor,
            "rif_receptor": rif_receptor,
            "subtotal": subtotal,
            "iva": iva,
            "igtf": igtf,
            "exento": exento,
            "total": total,
            "requiere_pie_legal_seniat": True,
            "pais": "VE",
        }


class CalculadoraNominaVE(CalculadoraNomina):
    """Nómina venezolana (LOTTT): delega en el motor puro de apps.nomina (Ola 5.2)."""

    def calcular(self, *, empleado, periodo, empresa) -> dict:
        from apps.nomina.services import calcular_nomina_empleado

        resultado = calcular_nomina_empleado(empleado, periodo)
        return resultado.as_dict()


class LibroLegalVE(LibroLegal):
    """Libros fiscales SENIAT (ventas y compras): delega en ``apps.fiscal.libros_seniat``."""

    def generar(self, *, empresa, periodo, tipo: str, formato: str = "txt"):
        if empresa is None:
            raise ValueError("La empresa es requerida para generar el libro legal VE.")

        tipo_norm = str(tipo or "").strip().lower()
        if tipo_norm not in {"ventas", "compras"}:
            raise ValueError(f"Tipo de libro legal inválido: {tipo!r}. Use 'ventas' o 'compras'.")

        formato_norm = str(formato or "txt").strip().lower()
        if formato_norm not in {"txt", "pdf"}:
            raise ValueError(f"Formato de libro legal inválido: {formato!r}. Use 'txt' o 'pdf'.")

        fecha_inicio, fecha_fin = _resolver_rango_periodo(periodo)

        from apps.fiscal.libros_seniat import (
            generar_libro_compras_pdf,
            generar_libro_compras_txt,
            generar_libro_ventas_pdf,
            generar_libro_ventas_txt,
        )

        if tipo_norm == "ventas":
            if formato_norm == "pdf":
                return generar_libro_ventas_pdf(empresa, fecha_inicio, fecha_fin)
            return generar_libro_ventas_txt(empresa, fecha_inicio, fecha_fin)

        if formato_norm == "pdf":
            return generar_libro_compras_pdf(empresa, fecha_inicio, fecha_fin)
        return generar_libro_compras_txt(empresa, fecha_inicio, fecha_fin)


# ── Capa de mercado (B) ───────────────────────────────────────────────────────


class ProveedorTasasVE(ProveedorTasas):
    """Consulta tasas de cambio vigentes en BD/caché sin llamadas HTTP externas."""

    def obtener_tasa(self, *, origen: str, destino: str, empresa: Any = None) -> Decimal | None:
        origen_norm = str(origen or "").strip().upper()
        destino_norm = str(destino or "").strip().upper()
        if not origen_norm or not destino_norm:
            return None
        if origen_norm == destino_norm:
            return Decimal("1")

        from apps.finanzas.services import TasaCambioError, obtener_tasa_cambio

        try:
            tasa = obtener_tasa_cambio(origen_norm, destino_norm, empresa=empresa)
        except TasaCambioError:
            return None

        valor = getattr(tasa, "valor_tasa", None)
        if valor is None:
            return None
        return valor if isinstance(valor, Decimal) else Decimal(str(valor))


class MetodosPagoLocalesVE(MetodosPagoLocales):
    """Lista los métodos de pago activos visibles para la empresa con metadatos VE."""

    def listar(self, *, empresa) -> list[dict]:
        if empresa is None:
            raise ValueError("La empresa es requerida para listar métodos de pago locales VE.")
        empresa_id = _empresa_pk(empresa)
        if empresa_id is None:
            raise ValueError("La empresa no tiene identificador válido.")

        from django.db.models import Q

        from apps.finanzas.models import MetodoPago, MetodoPagoEmpresaActiva
        from apps.fiscal.models import ConfiguracionFiscalEmpresa
        from apps.fiscal.services import METODOS_PAGO_IGTF

        legal_activa = bool(getattr(empresa, "localizacion_legal_activa", True))
        cfg_fiscal = ConfiguracionFiscalEmpresa.objects.filter(id_empresa_id=empresa_id).first()
        empresa_permite_igtf = legal_activa and (True if cfg_fiscal is None else bool(cfg_fiscal.aplica_igtf))

        desactivados_ids = MetodoPagoEmpresaActiva.objects.filter(
            empresa_id=empresa_id,
            activa=False,
        ).values_list("metodo_pago_id", flat=True)

        metodos = (
            MetodoPago.objects.filter(activo=True)
            .filter(Q(es_generico=True) | Q(es_publico=True) | Q(empresa__isnull=True) | Q(empresa_id=empresa_id))
            .exclude(id_metodo_pago__in=desactivados_ids)
            .prefetch_related("monedas")
            .order_by("nombre_metodo", "id_metodo_pago")
            .distinct()
        )

        return [
            _metadatos_metodo_pago_ve(
                metodo,
                empresa_permite_igtf=empresa_permite_igtf,
                metodos_igtf=METODOS_PAGO_IGTF,
            )
            for metodo in metodos
        ]
