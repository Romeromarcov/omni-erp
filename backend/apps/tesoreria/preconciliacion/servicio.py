"""Servicios transaccionales de pre-conciliación bancaria y cola de revisión humana."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .motor import (
    CENT,
    TIPO_CUENTA,
    TIPO_PAGO,
    VENTANA_DIAS_DEFAULT,
    MovimientoParaConciliar,
    PagoCandidato,
    PropuestaCalculada,
    ReglasCuentaConciliacion,
    pagos_candidatos_odoo,
    proponer_conciliacion,
    rifs,
)

if TYPE_CHECKING:
    from apps.core.models import Empresa, Usuarios
    from apps.finanzas.models import CuentaBancariaEmpresa, Pago
    from apps.tesoreria.models import (
        ConfiguracionConciliacionCuenta,
        MovimientoBancario,
        PropuestaConciliacionBancaria,
    )

logger = logging.getLogger(__name__)

ACCIONES_VALIDAS = frozenset({"APROBAR", "RECHAZAR", "CORREGIR", "REABRIR"})
ESTADOS_DECIDIDOS = frozenset({"APROBADA", "RECHAZADA", "CORREGIDA"})
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]+")


class PreconciliacionError(Exception):
    """Error de negocio o configuración en la pre-conciliación bancaria."""


class DecisionPreconciliacionInvalida(PreconciliacionError):
    """La decisión humana solicitada no es válida para el estado o datos actuales."""


def _limpiar_texto(valor: str | None) -> str:
    return _CTRL_RE.sub(" ", valor or "").strip()


def _construir_reglas_cuenta(
    empresa: "Empresa",
    cfg: "ConfiguracionConciliacionCuenta | None",
) -> ReglasCuentaConciliacion:
    rifs_empresa = rifs(getattr(empresa, "identificador_fiscal", "") or "")
    if cfg is None:
        return ReglasCuentaConciliacion(rifs_propios_empresa=rifs_empresa)

    def _resolver(fk_obj, codigo_txt: str) -> tuple[str | None, str]:
        if fk_obj is not None and getattr(fk_obj, "activo", True):
            etiqueta = f"{fk_obj.codigo_cuenta} {fk_obj.nombre_cuenta}".strip()
            return str(fk_obj.pk), etiqueta
        return None, _limpiar_texto(codigo_txt)

    com_id, com_cod = _resolver(cfg.id_cuenta_comisiones, cfg.codigo_cuenta_comisiones)
    igtf_id, igtf_cod = _resolver(cfg.id_cuenta_igtf, cfg.codigo_cuenta_igtf)
    tran_id, tran_cod = _resolver(
        cfg.id_cuenta_transito_pendientes, cfg.codigo_cuenta_transito_pendientes
    )
    ventana = max(0, min(int(cfg.ventana_dias), 30))
    return ReglasCuentaConciliacion(
        cuenta_comisiones_id=com_id,
        cuenta_comisiones_codigo=com_cod,
        cuenta_igtf_id=igtf_id,
        cuenta_igtf_codigo=igtf_cod,
        cuenta_transito_id=tran_id,
        cuenta_transito_codigo=tran_cod,
        ventana_dias=ventana,
        rifs_propios_empresa=rifs_empresa,
    )


def _extraer_socio_y_rifs_pago(
    pago: "Pago",
    rifs_propios: frozenset[str],
) -> tuple[str, frozenset[str]]:
    socio = ""
    textos_rif: list[str] = []

    for attr_doc in ("id_pedido", "id_nota_venta", "id_factura"):
        doc = getattr(pago, attr_doc, None)
        cliente = getattr(doc, "id_cliente", None) if doc is not None else None
        if cliente is not None:
            socio = socio or str(cliente.razon_social or "")
            if cliente.rif:
                textos_rif.append(str(cliente.rif))

    for attr_egr in ("id_cxp", "id_gasto"):
        doc_egr = getattr(pago, attr_egr, None)
        proveedor = getattr(doc_egr, "id_proveedor", None) if doc_egr is not None else None
        if proveedor is not None:
            socio = socio or str(proveedor.razon_social or "")
            if proveedor.rif:
                textos_rif.append(str(proveedor.rif))

    if pago.observaciones:
        textos_rif.append(str(pago.observaciones))

    conjunto_rifs: set[str] = set()
    for t in textos_rif:
        conjunto_rifs.update(rifs(t))
    conjunto_rifs -= set(rifs_propios)
    return socio, frozenset(conjunto_rifs)


def _etiqueta_pago_nativo(pago: "Pago") -> str:
    ref = (pago.referencia or "").strip()
    sufijo = f" ({ref})" if ref else f" #{str(pago.pk)[:8]}"
    return f"{pago.tipo_operacion} {pago.tipo_documento}{sufijo}"


def cargar_pagos_nativos_candidatos(
    *,
    empresa: "Empresa",
    cuenta_bancaria: "CuentaBancariaEmpresa",
    desde: date,
    hasta: date,
    ventana_dias: int = VENTANA_DIAS_DEFAULT,
    excluir_ids: frozenset[str] = frozenset(),
    rifs_propios: frozenset[str] = frozenset(),
) -> list[PagoCandidato]:
    """Carga pagos nativos de ``finanzas.Pago`` elegibles para la cuenta bancaria y ventana."""
    from apps.finanzas.models import Pago
    from apps.tesoreria.models import MovimientoBancario

    ventana = timedelta(days=max(0, int(ventana_dias)))
    fecha_min = desde - ventana
    fecha_max = hasta + ventana

    qs = (
        Pago.objects.filter(
            id_empresa=empresa,
            fecha_pago__date__gte=fecha_min,
            fecha_pago__date__lte=fecha_max,
        )
        .filter(
            models.Q(id_cuenta_bancaria=cuenta_bancaria)
            | models.Q(banco_destino=cuenta_bancaria)
        )
        .select_related(
            "id_moneda",
            "id_pedido__id_cliente",
            "id_nota_venta__id_cliente",
            "id_factura__id_cliente",
            "id_cxp__id_proveedor",
            "id_gasto__id_proveedor",
        )
        .order_by("fecha_pago", "id_pago")
    )

    pagos_lista = list(qs)
    if not pagos_lista:
        return []

    conciliados_ids = {
        str(pid)
        for pid in MovimientoBancario.objects.filter(
            id_empresa=empresa,
            activo=True,
            id_pago_conciliado_id__in=[p.pk for p in pagos_lista],
        ).values_list("id_pago_conciliado_id", flat=True)
    }

    moneda_cuenta_id = cuenta_bancaria.id_moneda_id
    salida: list[PagoCandidato] = []
    for p in pagos_lista:
        pid_str = str(p.pk)
        if pid_str in excluir_ids or pid_str in conciliados_ids:
            continue
        if moneda_cuenta_id and p.id_moneda_id and p.id_moneda_id != moneda_cuenta_id:
            continue
        fecha_local = (
            timezone.localtime(p.fecha_pago).date()
            if timezone.is_aware(p.fecha_pago)
            else p.fecha_pago.date()
        )
        socio, rifs_socio = _extraer_socio_y_rifs_pago(p, rifs_propios)
        memo_partes = [x.strip() for x in (p.referencia or "", p.observaciones or "") if x and x.strip()]
        salida.append(
            PagoCandidato(
                fuente="OMNI",
                pago_id=pid_str,
                nombre=_etiqueta_pago_nativo(p),
                fecha=fecha_local,
                monto=Decimal(str(p.monto)).quantize(CENT),
                entrante=p.tipo_operacion == "INGRESO",
                memo=" ".join(memo_partes),
                socio=socio,
                partner_rifs=rifs_socio,
                ya_conciliado=False,
            )
        )
    return salida


def _cargar_pagos_odoo_fuera_de_lock(
    *,
    empresa: "Empresa",
    cfg: "ConfiguracionConciliacionCuenta",
    desde: date,
    hasta: date,
    ventana_dias: int,
    excluir_externos: frozenset[str],
    rifs_propios: frozenset[str],
) -> list[PagoCandidato]:
    """Consulta pagos candidatos en Odoo sin mantener bloqueos de fila en PostgreSQL."""
    from apps.integration_hub.connectors.base import ConnectorConnectionError
    from apps.integration_hub.connectors.odoo.client import OdooAuthError, OdooCallError
    from apps.integration_hub.connectors.odoo.connector import OdooConnector

    conector = cfg.id_conector_odoo
    if (
        conector is None
        or not conector.activo
        or str(conector.id_empresa_id) != str(empresa.pk)
        or conector.id_proveedor is None
        or conector.id_proveedor.codigo != "odoo"
    ):
        raise PreconciliacionError(
            "La cuenta requiere un conector Odoo activo de la misma empresa para consultar pagos externos."
        )
    if not cfg.odoo_journal_id:
        raise PreconciliacionError(
            "Configure odoo_journal_id en la cuenta bancaria antes de consultar pagos de Odoo."
        )

    try:
        odoo_conn = OdooConnector(conector)
        cliente = odoo_conn._get_client()
        return pagos_candidatos_odoo(
            cliente.call,
            journal_id=int(cfg.odoo_journal_id),
            desde=desde,
            hasta=hasta,
            ventana_dias=ventana_dias,
            excluir_ids=excluir_externos,
            rifs_propios=rifs_propios,
        )
    except (
        ConnectorConnectionError,
        OdooAuthError,
        OdooCallError,
        ValueError,
        TypeError,
        KeyError,
        InvalidOperation,
    ) as exc:
        logger.warning(
            "Fallo consultando pagos candidatos en Odoo para empresa=%s cuenta=%s: %s",
            empresa.pk,
            cfg.id_cuenta_bancaria_id,
            type(exc).__name__,
        )
        raise PreconciliacionError(
            "No fue posible consultar los pagos candidatos en Odoo. Verifique la conexión del conector."
        ) from exc


def generar_propuestas_conciliacion(
    *,
    empresa: "Empresa",
    cuenta_bancaria: "CuentaBancariaEmpresa",
    desde: date | None = None,
    hasta: date | None = None,
    incluir_odoo: bool | None = None,
) -> dict[str, Any]:
    """Genera o refresca propuestas ``PENDIENTE`` sin sobrescribir decisiones humanas."""
    from apps.finanzas.models import CuentaBancariaEmpresa
    from apps.tesoreria.models import (
        ConfiguracionConciliacionCuenta,
        MovimientoBancario,
        PropuestaConciliacionBancaria,
    )

    if str(cuenta_bancaria.id_empresa_id) != str(empresa.pk):
        raise PreconciliacionError("La cuenta bancaria no pertenece a la empresa indicada.")
    if desde is not None and hasta is not None and desde > hasta:
        raise PreconciliacionError("La fecha 'desde' no puede ser posterior a 'hasta'.")

    cfg = (
        ConfiguracionConciliacionCuenta.objects.select_related(
            "id_cuenta_comisiones",
            "id_cuenta_igtf",
            "id_cuenta_transito_pendientes",
            "id_conector_odoo__id_proveedor",
        )
        .filter(id_empresa=empresa, id_cuenta_bancaria=cuenta_bancaria, activo=True)
        .first()
    )
    reglas = _construir_reglas_cuenta(empresa, cfg)
    usar_nativos = True if cfg is None else bool(cfg.incluir_pagos_nativos)
    usar_odoo = (
        bool(incluir_odoo)
        if incluir_odoo is not None
        else (bool(cfg.incluir_pagos_odoo) if cfg is not None else False)
    )
    if usar_odoo and cfg is None:
        raise PreconciliacionError(
            "Configure las reglas de conciliación de la cuenta (conector y diario Odoo) antes de activar incluir_odoo."
        )

    filtros_mov = models.Q(
        id_empresa=empresa,
        id_cuenta_bancaria=cuenta_bancaria,
        activo=True,
    )
    if desde is not None:
        filtros_mov &= models.Q(fecha_mov__gte=desde)
    if hasta is not None:
        filtros_mov &= models.Q(fecha_mov__lte=hasta)

    rango_fechas = MovimientoBancario.objects.filter(filtros_mov).aggregate(
        min_f=models.Min("fecha_mov"),
        max_f=models.Max("fecha_mov"),
    )
    if rango_fechas["min_f"] is None or rango_fechas["max_f"] is None:
        return {"nuevas": 0, "actualizadas": 0, "ya_decididas": 0, "total_evaluados": 0}

    pagos_odoo: list[PagoCandidato] = []
    if usar_odoo and cfg is not None:
        externos_comprometidos = frozenset(
            str(pid)
            for pid in PropuestaConciliacionBancaria.objects.filter(
                id_empresa=empresa,
                activo=True,
                estado__in=ESTADOS_DECIDIDOS,
                fuente_pago="ODOO",
            )
            .exclude(pago_externo_id="")
            .values_list("pago_externo_id", flat=True)
        )
        pagos_odoo = _cargar_pagos_odoo_fuera_de_lock(
            empresa=empresa,
            cfg=cfg,
            desde=rango_fechas["min_f"],
            hasta=rango_fechas["max_f"],
            ventana_dias=reglas.ventana_dias,
            excluir_externos=externos_comprometidos,
            rifs_propios=reglas.rifs_propios_empresa,
        )

    nuevas = 0
    actualizadas = 0
    ya_decididas = 0

    with transaction.atomic():
        CuentaBancariaEmpresa.objects.select_for_update().get(pk=cuenta_bancaria.pk)
        movimientos_qs = list(
            MovimientoBancario.objects.select_for_update()
            .filter(filtros_mov)
            .order_by("fecha_mov", "orden_en_archivo", "fecha_creacion", "id")
        )
        if not movimientos_qs:
            return {"nuevas": 0, "actualizadas": 0, "ya_decididas": 0, "total_evaluados": 0}

        existentes_por_mov: dict[str, PropuestaConciliacionBancaria] = {
            str(p.id_movimiento_bancario_id): p
            for p in PropuestaConciliacionBancaria.objects.select_for_update().filter(
                id_empresa=empresa,
                id_movimiento_bancario_id__in=[m.pk for m in movimientos_qs],
                activo=True,
            )
        }

        huerfanas_pks: list[Any] = []
        movs_evaluables: list[MovimientoParaConciliar] = []
        movs_mapa = {str(m.pk): m for m in movimientos_qs}
        for idx, m in enumerate(movimientos_qs):
            mid = str(m.pk)
            prop_existente = existentes_por_mov.get(mid)
            if prop_existente is not None and prop_existente.estado in ESTADOS_DECIDIDOS:
                ya_decididas += 1
                continue
            if m.estado != "PENDIENTE":
                if prop_existente is not None and prop_existente.estado == "PENDIENTE":
                    huerfanas_pks.append(prop_existente.pk)
                continue
            movs_evaluables.append(
                MovimientoParaConciliar(
                    movimiento_id=mid,
                    huella=m.huella or mid[:24],
                    fecha=m.fecha_mov,
                    orden=m.orden_en_archivo if m.orden_en_archivo is not None else idx,
                    es_credito=m.tipo == "CREDITO",
                    monto=Decimal(str(m.monto)),
                    referencia=m.referencia or "",
                    descripcion=m.descripcion or "",
                    categoria=m.categoria_clasificacion or "",
                    regla_clasificacion=m.regla_clasificacion or "",
                )
            )

        if huerfanas_pks:
            PropuestaConciliacionBancaria.objects.filter(pk__in=huerfanas_pks).update(
                activo=False, actualizada_en=timezone.now()
            )

        if not movs_evaluables:
            return {
                "nuevas": 0,
                "actualizadas": 0,
                "ya_decididas": ya_decididas,
                "total_evaluados": ya_decididas,
            }

        min_eval = min(m.fecha for m in movs_evaluables)
        max_eval = max(m.fecha for m in movs_evaluables)

        nativos_comprometidos = frozenset(
            str(pid)
            for pid in PropuestaConciliacionBancaria.objects.filter(
                id_empresa=empresa,
                activo=True,
                estado__in=ESTADOS_DECIDIDOS,
                id_pago_nativo__isnull=False,
            ).values_list("id_pago_nativo_id", flat=True)
        )
        externos_comprometidos_tx = frozenset(
            str(pid)
            for pid in PropuestaConciliacionBancaria.objects.filter(
                id_empresa=empresa,
                activo=True,
                estado__in=ESTADOS_DECIDIDOS,
                fuente_pago="ODOO",
            )
            .exclude(pago_externo_id="")
            .values_list("pago_externo_id", flat=True)
        )

        candidatos_totales: list[PagoCandidato] = []
        if usar_nativos:
            candidatos_totales.extend(
                cargar_pagos_nativos_candidatos(
                    empresa=empresa,
                    cuenta_bancaria=cuenta_bancaria,
                    desde=min_eval,
                    hasta=max_eval,
                    ventana_dias=reglas.ventana_dias,
                    excluir_ids=nativos_comprometidos,
                    rifs_propios=reglas.rifs_propios_empresa,
                )
            )
        if usar_odoo:
            candidatos_totales.extend(
                p for p in pagos_odoo if p.pago_id not in externos_comprometidos_tx
            )

        calculadas: list[PropuestaCalculada] = proponer_conciliacion(
            movs_evaluables, candidatos_totales, reglas
        )

        for calc in calculadas:
            valores_campos: dict[str, Any] = {
                "tipo": calc.tipo,
                "regla": calc.regla,
                "motivo": calc.motivo[:500],
                "fuente_pago": calc.fuente_pago,
                "id_pago_nativo_id": calc.pago_id if calc.fuente_pago == "OMNI" and calc.pago_id else None,
                "pago_externo_id": calc.pago_id if calc.fuente_pago == "ODOO" else "",
                "pago_nombre": calc.pago_nombre[:200],
                "pago_socio": calc.pago_socio[:255],
                "id_cuenta_contable_id": calc.cuenta_id or None,
                "cuenta_contable_codigo": calc.cuenta_codigo[:150],
                "puntaje": calc.puntaje,
                "candidatos_json": calc.candidatos,
            }
            actual = existentes_por_mov.get(calc.movimiento_id)
            if actual is None:
                try:
                    with transaction.atomic():
                        PropuestaConciliacionBancaria.objects.create(
                            id_empresa=empresa,
                            id_movimiento_bancario=movs_mapa[calc.movimiento_id],
                            estado="PENDIENTE",
                            **valores_campos,
                        )
                    nuevas += 1
                except IntegrityError:
                    existente_conc = (
                        PropuestaConciliacionBancaria.objects.select_for_update()
                        .filter(
                            id_empresa=empresa,
                            id_movimiento_bancario=movs_mapa[calc.movimiento_id],
                            activo=True,
                        )
                        .first()
                    )
                    if existente_conc is not None and existente_conc.estado == "PENDIENTE":
                        for k, v in valores_campos.items():
                            setattr(existente_conc, k, v)
                        existente_conc.save(update_fields=[*valores_campos.keys(), "actualizada_en"])
                        actualizadas += 1
                    else:
                        ya_decididas += 1
            elif actual.estado == "PENDIENTE":
                for k, v in valores_campos.items():
                    setattr(actual, k, v)
                actual.save(update_fields=[*valores_campos.keys(), "actualizada_en"])
                actualizadas += 1
            else:
                ya_decididas += 1

    return {
        "nuevas": nuevas,
        "actualizadas": actualizadas,
        "ya_decididas": ya_decididas,
        "total_evaluados": nuevas + actualizadas + ya_decididas,
    }


def _snapshot_propuesta(prop: "PropuestaConciliacionBancaria") -> dict[str, Any]:
    return {
        "tipo": prop.tipo,
        "regla": prop.regla,
        "fuente_pago": prop.fuente_pago,
        "id_pago_nativo": str(prop.id_pago_nativo_id) if prop.id_pago_nativo_id else None,
        "pago_externo_id": prop.pago_externo_id,
        "pago_nombre": prop.pago_nombre,
        "pago_socio": prop.pago_socio,
        "id_cuenta_contable": str(prop.id_cuenta_contable_id) if prop.id_cuenta_contable_id else None,
        "cuenta_contable_codigo": prop.cuenta_contable_codigo,
        "estado": prop.estado,
    }


def _verificar_periodo_abierto(empresa: "Empresa", cuenta_id: Any, fecha_mov: date) -> None:
    from apps.tesoreria.models import ConciliacionBancaria

    cerrada = ConciliacionBancaria.objects.filter(
        id_empresa=empresa,
        id_cuenta_bancaria_id=cuenta_id,
        periodo_inicio__lte=fecha_mov,
        periodo_fin__gte=fecha_mov,
        estado="CERRADA",
    ).exists()
    if cerrada:
        raise DecisionPreconciliacionInvalida(
            "El período de conciliación bancaria para esta fecha ya se encuentra cerrado."
        )


def _validar_compatibilidad_pago_nativo(
    *,
    empresa: "Empresa",
    mov: "MovimientoBancario",
    cuenta_bancaria: "CuentaBancariaEmpresa",
    pago_obj: "Pago",
) -> None:
    """Garantiza integridad contable (sentido, moneda, cuenta y unicidad) entre movimiento y Pago."""
    from apps.tesoreria.models import MovimientoBancario

    es_credito = mov.tipo == "CREDITO"
    es_ingreso = pago_obj.tipo_operacion == "INGRESO"
    if es_credito != es_ingreso:
        raise DecisionPreconciliacionInvalida(
            "El sentido contable del pago no coincide con el movimiento bancario "
            "(crédito exige ingreso; débito exige egreso)."
        )

    if (
        cuenta_bancaria.id_moneda_id
        and pago_obj.id_moneda_id
        and str(cuenta_bancaria.id_moneda_id) != str(pago_obj.id_moneda_id)
    ):
        raise DecisionPreconciliacionInvalida(
            "La moneda del pago nativo no coincide con la moneda de la cuenta bancaria."
        )

    cuentas_pago = {
        str(cid)
        for cid in (pago_obj.id_cuenta_bancaria_id, pago_obj.banco_destino_id)
        if cid is not None
    }
    if cuentas_pago and str(mov.id_cuenta_bancaria_id) not in cuentas_pago:
        raise DecisionPreconciliacionInvalida(
            "El pago nativo pertenece a otra cuenta bancaria distinta a la del movimiento."
        )

    if (
        MovimientoBancario.objects.filter(
            id_empresa=empresa, id_pago_conciliado=pago_obj, activo=True
        )
        .exclude(pk=mov.pk)
        .exists()
    ):
        raise DecisionPreconciliacionInvalida(
            "El pago nativo indicado ya está conciliado con otro movimiento bancario."
        )


def decidir_propuesta_conciliacion(
    *,
    empresa: "Empresa",
    propuesta_id: str,
    accion: str,
    usuario: "Usuarios | None",
    pago_nativo_id: str | None = None,
    pago_externo_id: str | None = None,
    pago_nombre: str | None = None,
    cuenta_contable_id: str | None = None,
    cuenta_contable_codigo: str | None = None,
    comentario: str | None = None,
) -> "PropuestaConciliacionBancaria":
    """Aplica una decisión humana (APROBAR/RECHAZAR/CORREGIR/REABRIR) y registra auditoría inmutable."""
    from apps.contabilidad.models import PlanCuentas
    from apps.finanzas.models import CuentaBancariaEmpresa, Pago
    from apps.tesoreria.models import (
        DecisionPreconciliacionBancaria,
        MovimientoBancario,
        PropuestaConciliacionBancaria,
    )

    accion_norm = _limpiar_texto(accion).upper()
    if accion_norm not in ACCIONES_VALIDAS:
        raise DecisionPreconciliacionInvalida(
            f"Acción desconocida: '{accion_norm}'. Use APROBAR, RECHAZAR, CORREGIR o REABRIR."
        )

    comentario_limpio = _limpiar_texto(comentario)
    pago_ext_limpio = _limpiar_texto(pago_externo_id)
    pago_nom_limpio = _limpiar_texto(pago_nombre)
    cuenta_cod_limpio = _limpiar_texto(cuenta_contable_codigo)

    if accion_norm in ("RECHAZAR", "REABRIR") and not comentario_limpio:
        raise DecisionPreconciliacionInvalida(
            f"La acción {accion_norm} exige indicar un comentario de auditoría."
        )

    tiene_pago_nativo = bool(pago_nativo_id)
    tiene_pago_externo = bool(pago_ext_limpio)
    tiene_pago = tiene_pago_nativo or tiene_pago_externo
    tiene_cuenta = bool(cuenta_contable_id) or bool(cuenta_cod_limpio)

    if accion_norm == "CORREGIR":
        if tiene_pago_nativo and tiene_pago_externo:
            raise DecisionPreconciliacionInvalida(
                "Indique un pago nativo o un pago externo, no ambos simultáneamente."
            )
        if tiene_pago == tiene_cuenta:
            raise DecisionPreconciliacionInvalida(
                "La acción CORREGIR exige indicar exclusivamente un pago o una cuenta contable."
            )

    usuario_autenticado = usuario if (usuario is not None and usuario.is_authenticated) else None
    nombre_actor = (
        getattr(usuario_autenticado, "username", "") or str(usuario_autenticado.pk)
        if usuario_autenticado is not None
        else "sistema"
    )

    ref_ids = (
        PropuestaConciliacionBancaria.objects.filter(
            pk=propuesta_id, id_empresa=empresa, activo=True
        )
        .values_list(
            "id_movimiento_bancario_id",
            "id_movimiento_bancario__id_cuenta_bancaria_id",
        )
        .first()
    )
    if ref_ids is None:
        raise PreconciliacionError("Propuesta de conciliación no encontrada.")
    mov_id, cuenta_id = ref_ids

    with transaction.atomic():
        # Orden canónico de bloqueos en PostgreSQL: CuentaBancariaEmpresa -> MovimientoBancario -> Propuesta
        cuenta_locked = CuentaBancariaEmpresa.objects.select_for_update().get(pk=cuenta_id)
        mov = MovimientoBancario.objects.select_for_update().get(pk=mov_id)
        prop = (
            PropuestaConciliacionBancaria.objects.select_for_update()
            .filter(pk=propuesta_id, id_empresa=empresa, activo=True)
            .first()
        )
        if prop is None:
            raise PreconciliacionError("Propuesta de conciliación no encontrada.")

        if not mov.activo or mov.estado == "DESCARTADO":
            raise DecisionPreconciliacionInvalida(
                "El movimiento bancario asociado está inactivo o descartado."
            )

        _verificar_periodo_abierto(empresa, mov.id_cuenta_bancaria_id, mov.fecha_mov)
        estado_anterior = _snapshot_propuesta(prop)
        ahora = timezone.now()

        if accion_norm == "REABRIR":
            if prop.estado == "PENDIENTE":
                raise DecisionPreconciliacionInvalida("La propuesta ya se encuentra en estado PENDIENTE.")
            prop.estado = "PENDIENTE"
            prop.decidida_por = None
            prop.decidida_en = None
            prop.ultimo_comentario = comentario_limpio
            if mov.estado == "CONCILIADO":
                mov.estado = "PENDIENTE"
                mov.id_pago_conciliado = None
                mov.save(update_fields=["estado", "id_pago_conciliado"])
        else:
            if prop.estado != "PENDIENTE":
                raise DecisionPreconciliacionInvalida(
                    f"La propuesta ya fue decidida ({prop.estado}). Reábrala antes de registrar otra decisión."
                )
            if mov.estado != "PENDIENTE":
                raise DecisionPreconciliacionInvalida(
                    "El movimiento bancario ya se encuentra conciliado fuera de esta propuesta."
                )

            if accion_norm == "APROBAR":
                if prop.tipo not in (TIPO_PAGO, TIPO_CUENTA):
                    raise DecisionPreconciliacionInvalida(
                        "No hay pago ni cuenta propuesta para aprobar; utilice CORREGIR."
                    )
                if prop.tipo == TIPO_CUENTA and prop.id_cuenta_contable_id:
                    cuenta_activa = PlanCuentas.objects.filter(
                        pk=prop.id_cuenta_contable_id, id_empresa=empresa, activo=True
                    ).exists()
                    if not cuenta_activa:
                        raise DecisionPreconciliacionInvalida(
                            "La cuenta contable propuesta está inactiva o ya no pertenece a la empresa."
                        )
                pago_conciliar = None
                if prop.tipo == TIPO_PAGO and prop.id_pago_nativo_id:
                    pago_conciliar = (
                        Pago.objects.select_for_update()
                        .filter(pk=prop.id_pago_nativo_id, id_empresa=empresa)
                        .first()
                    )
                    if pago_conciliar is None:
                        raise DecisionPreconciliacionInvalida(
                            "El pago nativo propuesto ya no está disponible en esta empresa."
                        )
                    _validar_compatibilidad_pago_nativo(
                        empresa=empresa,
                        mov=mov,
                        cuenta_bancaria=cuenta_locked,
                        pago_obj=pago_conciliar,
                    )
                prop.estado = "APROBADA"
                prop.decidida_por = usuario_autenticado
                prop.decidida_en = ahora
                prop.ultimo_comentario = comentario_limpio
                mov.estado = "CONCILIADO"
                mov.id_pago_conciliado = pago_conciliar
                mov.save(update_fields=["estado", "id_pago_conciliado"])

            elif accion_norm == "RECHAZAR":
                prop.estado = "RECHAZADA"
                prop.decidida_por = usuario_autenticado
                prop.decidida_en = ahora
                prop.ultimo_comentario = comentario_limpio

            elif accion_norm == "CORREGIR":
                if pago_nativo_id:
                    pago_obj = (
                        Pago.objects.select_for_update(of=("self",))
                        .select_related(
                            "id_pedido__id_cliente",
                            "id_nota_venta__id_cliente",
                            "id_factura__id_cliente",
                            "id_cxp__id_proveedor",
                            "id_gasto__id_proveedor",
                        )
                        .filter(pk=pago_nativo_id, id_empresa=empresa)
                        .first()
                    )
                    if pago_obj is None:
                        raise DecisionPreconciliacionInvalida(
                            "El pago nativo indicado no existe o no pertenece a la empresa."
                        )
                    _validar_compatibilidad_pago_nativo(
                        empresa=empresa,
                        mov=mov,
                        cuenta_bancaria=cuenta_locked,
                        pago_obj=pago_obj,
                    )
                    socio_pago, _ = _extraer_socio_y_rifs_pago(
                        pago_obj, rifs(getattr(empresa, "identificador_fiscal", "") or "")
                    )
                    prop.tipo = TIPO_PAGO
                    prop.fuente_pago = "OMNI"
                    prop.id_pago_nativo = pago_obj
                    prop.pago_externo_id = ""
                    prop.pago_nombre = (pago_nom_limpio or _etiqueta_pago_nativo(pago_obj))[:200]
                    prop.pago_socio = socio_pago[:255]
                    prop.id_cuenta_contable = None
                    prop.cuenta_contable_codigo = ""
                    mov.estado = "CONCILIADO"
                    mov.id_pago_conciliado = pago_obj
                    mov.save(update_fields=["estado", "id_pago_conciliado"])
                elif tiene_pago_externo:
                    info_cand: dict[str, Any] = next(
                        (
                            c
                            for c in (prop.candidatos_json or [])
                            if c.get("fuente") == "ODOO" and str(c.get("id")) == pago_ext_limpio
                        ),
                        {},
                    )
                    prop.tipo = TIPO_PAGO
                    prop.fuente_pago = "ODOO"
                    prop.id_pago_nativo = None
                    prop.pago_externo_id = pago_ext_limpio[:64]
                    prop.pago_nombre = _limpiar_texto(
                        pago_nom_limpio or str(info_cand.get("nombre") or f"ODOO-{pago_ext_limpio}")
                    )[:200]
                    prop.pago_socio = _limpiar_texto(str(info_cand.get("socio") or ""))[:255]
                    prop.id_cuenta_contable = None
                    prop.cuenta_contable_codigo = ""
                    mov.estado = "CONCILIADO"
                    mov.id_pago_conciliado = None
                    mov.save(update_fields=["estado", "id_pago_conciliado"])
                else:
                    cuenta_obj = None
                    etiqueta_cuenta = cuenta_cod_limpio
                    if cuenta_contable_id:
                        cuenta_obj = PlanCuentas.objects.filter(
                            pk=cuenta_contable_id, id_empresa=empresa, activo=True
                        ).first()
                        if cuenta_obj is None:
                            raise DecisionPreconciliacionInvalida(
                                "La cuenta contable indicada no existe, está inactiva o pertenece a otra empresa."
                            )
                        if not etiqueta_cuenta:
                            etiqueta_cuenta = (
                                f"{cuenta_obj.codigo_cuenta} {cuenta_obj.nombre_cuenta}".strip()
                            )
                    prop.tipo = TIPO_CUENTA
                    prop.fuente_pago = ""
                    prop.id_pago_nativo = None
                    prop.pago_externo_id = ""
                    prop.pago_nombre = ""
                    prop.pago_socio = ""
                    prop.id_cuenta_contable = cuenta_obj
                    prop.cuenta_contable_codigo = etiqueta_cuenta[:150]
                    mov.estado = "CONCILIADO"
                    mov.id_pago_conciliado = None
                    mov.save(update_fields=["estado", "id_pago_conciliado"])

                prop.estado = "CORREGIDA"
                prop.decidida_por = usuario_autenticado
                prop.decidida_en = ahora
                prop.ultimo_comentario = comentario_limpio

        try:
            with transaction.atomic():
                prop.save()
        except IntegrityError as exc:
            raise DecisionPreconciliacionInvalida(
                "El pago seleccionado ya se encuentra aprobado o asignado a otro movimiento bancario."
            ) from exc

        estado_nuevo = _snapshot_propuesta(prop)
        DecisionPreconciliacionBancaria.objects.create(
            id_empresa=empresa,
            id_propuesta=prop,
            id_movimiento_bancario=mov,
            accion=accion_norm,
            estado_anterior_json=estado_anterior,
            estado_nuevo_json=estado_nuevo,
            comentario=comentario_limpio,
            id_usuario=usuario_autenticado,
            usuario_nombre=nombre_actor[:150],
        )

    return prop


def contactos_por_rif_nativos(
    empresa: "Empresa",
    buscados: list[str] | set[str] | frozenset[str],
) -> dict[str, str]:
    """RIF/cédula -> razón social en Omni cuando exactamente UN tercero lo posee en la empresa."""
    from apps.core.models import Contacto
    from apps.crm.models import Cliente
    from apps.proveedores.models import Proveedor

    rifs_propios = rifs(getattr(empresa, "identificador_fiscal", "") or "")
    objetivo = sorted(set(buscados) - set(rifs_propios))
    if not objetivo:
        return {}

    hallados: dict[str, set[str]] = {}
    fragmentos = sorted({r[1:-1] for r in objetivo if len(r) >= 3 and r[1:-1]})
    if not fragmentos:
        return {}

    for i in range(0, len(fragmentos), 200):
        lote = fragmentos[i : i + 200]
        q_rif = models.Q()
        q_contacto = models.Q()
        for frag in lote:
            q_rif |= models.Q(rif__icontains=frag)
            q_contacto |= models.Q(rif__icontains=frag) | models.Q(cedula__icontains=frag)

        for rif_txt, razon in (
            Cliente.objects.filter(id_empresa=empresa, activo=True)
            .filter(q_rif)
            .values_list("rif", "razon_social")
        ):
            for r_norm in rifs(rif_txt) & set(objetivo):
                if razon:
                    hallados.setdefault(r_norm, set()).add(str(razon).strip())

        for rif_txt, razon in (
            Proveedor.objects.filter(id_empresa=empresa, activo=True)
            .filter(q_rif)
            .values_list("rif", "razon_social")
        ):
            for r_norm in rifs(rif_txt) & set(objetivo):
                if razon:
                    hallados.setdefault(r_norm, set()).add(str(razon).strip())

        for c in (
            Contacto.objects.filter(id_empresa=empresa, activo=True)
            .filter(q_contacto)
            .only("rif", "cedula", "nombre", "apellido", "nombre_comercial", "tipo_persona")
        ):
            etiqueta = c.nombre_completo.strip()
            if not etiqueta:
                continue
            for r_norm in (rifs(c.rif) | rifs(c.cedula)) & set(objetivo):
                hallados.setdefault(r_norm, set()).add(etiqueta)

    return {r_k: next(iter(nombres)) for r_k, nombres in hallados.items() if len(nombres) == 1}
