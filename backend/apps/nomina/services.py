"""Orquestación de nómina (Ola 5.2 + CTF-013).

Mapea entidades del ORM (Empleado, PeriodoNomina) a la entrada del motor de
cálculo PURO `calculo_lottt` y devuelve el resultado. La lógica monetaria vive
en `calculo_lottt` (sin I/O, testeable); aquí solo se extraen datos.

`procesar_proceso_nomina` es la orquestación completa del proceso (CTF-013):
calcula la nómina LOTTT de cada empleado activo, persiste `Nomina` +
`DetalleNomina`, totaliza el `ProcesoNomina` y genera el asiento contable
`NOMINA` (R-CODE-11) — todo dentro de UNA transacción atómica.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .calculo_lottt import EntradaNomina, ParametrosLOTTT, ResultadoNomina, calcular_nomina

logger = logging.getLogger(__name__)


class NominaProcesoError(Exception):
    """Error de negocio al procesar un proceso de nómina (→ 400 en la API)."""


# ── Parámetros por empresa (ParametroSistema) ────────────────────────────────
#
# Códigos en `configuracion_motor.ParametroSistema` (tipo_dato NUMERO salvo bool):
#   nomina.salario_minimo      → fallback de salario mensual si el empleado no
#                                tiene salario propio (decreto vigente)
#   nomina.cestaticket_mensual → bono de alimentación mensual por empleado
#   nomina.valor_ut            → valor de la Unidad Tributaria (ISLR)
#   nomina.aplica_islr         → "true"/"false": activa la retención de ISLR

PARAM_SALARIO_MINIMO = "nomina.salario_minimo"
PARAM_CESTATICKET = "nomina.cestaticket_mensual"
PARAM_VALOR_UT = "nomina.valor_ut"
PARAM_APLICA_ISLR = "nomina.aplica_islr"


def _leer_parametro(empresa, codigo: str) -> str | None:
    from apps.configuracion_motor.models import ParametroSistema  # noqa: PLC0415

    try:
        param = ParametroSistema.objects.get(id_empresa=empresa, codigo_parametro=codigo, activo=True)
    except ParametroSistema.DoesNotExist:
        return None
    return param.valor_parametro.strip()


def _parametro_decimal(empresa, codigo: str, default: Decimal) -> Decimal:
    valor = _leer_parametro(empresa, codigo)
    if valor is None:
        return default
    try:
        return Decimal(valor)
    except InvalidOperation:
        logger.warning("ParametroSistema %s inválido (%r) para empresa=%s; uso default", codigo, valor, empresa.pk)
        return default


@dataclass(frozen=True)
class ConfigNominaEmpresa:
    """Parámetros LOTTT actualizables por empresa (salario mínimo, UT, cestaticket)."""

    parametros: ParametrosLOTTT
    salario_minimo: Decimal
    cestaticket_mensual: Decimal


def config_nomina_de_empresa(empresa) -> ConfigNominaEmpresa:
    """Construye los parámetros LOTTT de la empresa desde `ParametroSistema`.

    Los defaults del motor (`ParametrosLOTTT`) aplican cuando el parámetro no
    está configurado; así salario mínimo, UT y cestaticket se actualizan por
    decreto sin tocar código (Plan Maestro §6.2).
    """
    defaults = ParametrosLOTTT()
    valor_ut = _parametro_decimal(empresa, PARAM_VALOR_UT, defaults.valor_ut)
    aplica_islr_raw = _leer_parametro(empresa, PARAM_APLICA_ISLR)
    aplica_islr = (
        defaults.aplica_islr
        if aplica_islr_raw is None
        else aplica_islr_raw.lower() in ("true", "1", "si", "sí", "yes")
    )
    return ConfigNominaEmpresa(
        parametros=ParametrosLOTTT(valor_ut=valor_ut, aplica_islr=aplica_islr),
        salario_minimo=_parametro_decimal(empresa, PARAM_SALARIO_MINIMO, Decimal("0")),
        cestaticket_mensual=_parametro_decimal(empresa, PARAM_CESTATICKET, Decimal("0")),
    )


def _salario_mensual(empleado) -> Decimal:
    """Lee el salario mensual del empleado de forma defensiva (varios nombres
    posibles según evolucione el modelo de rrhh; `documento_json` como puente
    mientras rrhh.Empleado no tiene campo de salario propio)."""
    for attr in ("salario_mensual", "sueldo_base", "salario_base", "salario"):
        val = getattr(empleado, attr, None)
        if val is not None:
            return Decimal(str(val))
    doc = getattr(empleado, "documento_json", None)
    if isinstance(doc, dict):
        for key in ("salario_mensual", "sueldo_base", "salario_base", "salario"):
            if doc.get(key) is not None:
                try:
                    return Decimal(str(doc[key]))
                except InvalidOperation:
                    logger.warning("documento_json.%s inválido para empleado=%s", key, empleado.pk)
    return Decimal("0")


def _antiguedad_anios(empleado, periodo) -> int:
    fecha_ingreso = getattr(empleado, "fecha_ingreso", None)
    fecha_corte = getattr(periodo, "fecha_fin", None) or getattr(periodo, "fecha_pago", None)
    if not fecha_ingreso or not fecha_corte:
        return 0
    return max((fecha_corte - fecha_ingreso).days // 365, 0)


def entrada_desde_empleado(
    empleado,
    periodo,
    *,
    dias_trabajados: int = 30,
    horas_extra_diurnas: Decimal = Decimal("0"),
    horas_extra_nocturnas: Decimal = Decimal("0"),
    horas_nocturnas: Decimal = Decimal("0"),
    cestaticket_mensual: Decimal = Decimal("0"),
    otras_asignaciones: Decimal = Decimal("0"),
    otras_deducciones: Decimal = Decimal("0"),
) -> EntradaNomina:
    return EntradaNomina(
        salario_mensual=_salario_mensual(empleado),
        dias_trabajados=dias_trabajados,
        horas_extra_diurnas=horas_extra_diurnas,
        horas_extra_nocturnas=horas_extra_nocturnas,
        horas_nocturnas=horas_nocturnas,
        antiguedad_anios=_antiguedad_anios(empleado, periodo),
        cestaticket_mensual=cestaticket_mensual,
        otras_asignaciones=otras_asignaciones,
        otras_deducciones=otras_deducciones,
    )


def calcular_nomina_empleado(
    empleado,
    periodo,
    *,
    parametros: ParametrosLOTTT | None = None,
    **kwargs,
) -> ResultadoNomina:
    """Calcula la nómina LOTTT de un empleado para un período (Decimal end-to-end)."""
    entrada = entrada_desde_empleado(empleado, periodo, **kwargs)
    return calcular_nomina(entrada, parametros)


# ── Procesamiento del proceso de nómina (CTF-013) ────────────────────────────
#
# Conceptos estándar que el proceso materializa como DetalleNomina. Se crean
# con get_or_create por empresa (idempotente, multi-tenant).
CONCEPTOS_LOTTT = {
    # codigo: (nombre, tipo_concepto, categoria, campo de ResultadoNomina)
    "SUELDO": ("Sueldo del período", "DEVENGADO", "SUELDO_BASE", "salario_periodo"),
    "HED": ("Horas extra diurnas (50%)", "DEVENGADO", "HORAS_EXTRAS", "monto_horas_extra_diurnas"),
    "HEN": ("Horas extra nocturnas (100%)", "DEVENGADO", "HORAS_EXTRAS", "monto_horas_extra_nocturnas"),
    "BONO_NOCT": ("Bono nocturno (30%)", "DEVENGADO", "BONO", "monto_bono_nocturno"),
    "OTRAS_ASIG": ("Otras asignaciones", "DEVENGADO", "OTROS", "otras_asignaciones"),
    "CESTATICKET": ("Cestaticket / bono de alimentación", "DEVENGADO", "OTROS", "cestaticket"),
    "SSO": ("Retención SSO (4%)", "DEDUCCION", "SEGURO_SOCIAL", "sso"),
    "FAOV": ("Retención FAOV (1%)", "DEDUCCION", "OTROS", "faov"),
    "RPE": ("Retención RPE / paro forzoso (0.5%)", "DEDUCCION", "OTROS", "rpe"),
    "ISLR": ("Retención ISLR", "DEDUCCION", "IMPUESTO_RENTA", "islr"),
    "OTRAS_DED": ("Otras deducciones", "DEDUCCION", "OTROS", "otras_deducciones"),
    "AP_SSO": ("Aporte patronal SSO (9%)", "APORTE_PATRONAL", "SEGURO_SOCIAL", "aporte_patronal_sso"),
    "AP_FAOV": ("Aporte patronal FAOV (2%)", "APORTE_PATRONAL", "OTROS", "aporte_patronal_faov"),
    "AP_INCES": ("Aporte patronal INCES (2%)", "APORTE_PATRONAL", "OTROS", "aporte_patronal_inces"),
    "AP_RPE": ("Aporte patronal RPE (2%)", "APORTE_PATRONAL", "OTROS", "aporte_patronal_rpe"),
}

_CAMPOS_DATOS_EMPLEADO = (
    "dias_trabajados",
    "horas_extra_diurnas",
    "horas_extra_nocturnas",
    "horas_nocturnas",
    "otras_asignaciones",
    "otras_deducciones",
    "salario_mensual",
)


def _conceptos_de_empresa(empresa) -> dict:
    """Garantiza los ConceptoNomina estándar de la empresa (idempotente)."""
    from .models import ConceptoNomina  # noqa: PLC0415

    conceptos = {}
    for codigo, (nombre, tipo, categoria, _campo) in CONCEPTOS_LOTTT.items():
        concepto, _ = ConceptoNomina.objects.get_or_create(
            id_empresa=empresa,
            codigo_concepto=codigo,
            defaults={"nombre_concepto": nombre, "tipo_concepto": tipo, "categoria": categoria},
        )
        conceptos[codigo] = concepto
    return conceptos


def _datos_de_empleado(datos_empleados: dict | None, empleado) -> dict:
    """Extrae y valida los datos variables (horas extra, días…) de un empleado.

    `datos_empleados` viene del request: {"<id_empleado>": {"horas_extra_diurnas": "4", ...}}.
    """
    if not datos_empleados:
        return {}
    crudo = datos_empleados.get(str(empleado.pk)) or {}
    if not isinstance(crudo, dict):
        raise NominaProcesoError(f"Datos inválidos para el empleado {empleado.pk}: se esperaba un objeto.")
    datos: dict = {}
    for campo in _CAMPOS_DATOS_EMPLEADO:
        if campo not in crudo:
            continue
        try:
            if campo == "dias_trabajados":
                datos[campo] = int(crudo[campo])
            else:
                datos[campo] = Decimal(str(crudo[campo]))
        except (InvalidOperation, TypeError, ValueError):
            raise NominaProcesoError(
                f"Valor inválido en '{campo}' para el empleado {empleado.pk}: {crudo[campo]!r}"
            ) from None
    desconocidos = set(crudo) - set(_CAMPOS_DATOS_EMPLEADO)
    if desconocidos:
        raise NominaProcesoError(
            f"Campos no soportados para el empleado {empleado.pk}: {sorted(desconocidos)}. "
            f"Soportados: {sorted(_CAMPOS_DATOS_EMPLEADO)}"
        )
    return datos


@transaction.atomic
def procesar_proceso_nomina(proceso, datos_empleados: dict | None = None, usuario=None):
    """Procesa un ProcesoNomina completo (CTF-013, TEST-5 nómina). Atómico.

    Para cada empleado activo de la empresa: calcula la nómina LOTTT (motor puro
    `calculo_lottt` con parámetros de `ParametroSistema`), crea `Nomina` +
    `DetalleNomina`, totaliza el proceso y genera el asiento contable `NOMINA`
    (R-CODE-11, monto = total neto a pagar) en la MISMA transacción. Cualquier
    fallo (empleado sin salario, datos inválidos, asiento con contabilidad
    activa sin mapeo) revierte TODO el proceso.

    Contrato de re-proceso: solo procesa procesos en estado EN_PROCESO. Un
    proceso COMPLETADO/APROBADO/CANCELADO devuelve error (la API responde 400);
    para recalcular se cancela y se crea un proceso nuevo — no se regeneran
    recibos en sitio (los recibos emitidos son inmutables).

    Returns:
        (proceso actualizado, asiento|None, advertencia_asiento|None)
    """
    from apps.contabilidad.services import generar_asiento_o_fallar  # noqa: PLC0415
    from apps.rrhh.models import Empleado  # noqa: PLC0415

    from .calculo_lottt import q  # noqa: PLC0415
    from .models import DetalleNomina, Nomina, ProcesoNomina  # noqa: PLC0415

    # Lock del proceso: evita doble procesamiento concurrente del mismo proceso.
    proceso = ProcesoNomina.objects.select_for_update().select_related("id_empresa", "id_periodo_nomina").get(
        pk=proceso.pk
    )
    if proceso.estado != "EN_PROCESO":
        raise NominaProcesoError(
            f"El proceso está en estado {proceso.estado}; solo se procesan procesos EN_PROCESO. "
            "Para recalcular, cancele este proceso y cree uno nuevo."
        )

    empresa = proceso.id_empresa
    periodo = proceso.id_periodo_nomina
    empleados = list(Empleado.objects.filter(empresa=empresa, activo=True).order_by("apellido", "nombre"))
    if not empleados:
        raise NominaProcesoError("La empresa no tiene empleados activos para procesar.")

    config = config_nomina_de_empresa(empresa)
    conceptos = _conceptos_de_empresa(empresa)
    ahora = timezone.now()

    total_devengado = Decimal("0")
    total_deducciones = Decimal("0")
    total_neto = Decimal("0")

    for empleado in empleados:
        datos = _datos_de_empleado(datos_empleados, empleado)
        salario = datos.pop("salario_mensual", None) or _salario_mensual(empleado) or config.salario_minimo
        if salario <= 0:
            raise NominaProcesoError(
                f"El empleado {empleado.nombre} {empleado.apellido} ({empleado.cedula}) no tiene salario "
                f"definido y no hay parámetro '{PARAM_SALARIO_MINIMO}' configurado para la empresa."
            )
        entrada = EntradaNomina(
            salario_mensual=salario,
            antiguedad_anios=_antiguedad_anios(empleado, periodo),
            cestaticket_mensual=config.cestaticket_mensual,
            **datos,
        )
        resultado = calcular_nomina(entrada, config.parametros)

        nomina = Nomina.objects.create(
            id_proceso_nomina=proceso,
            id_empleado=empleado,
            sueldo_base=salario,
            total_devengado=resultado.total_asignaciones,
            total_deducciones=resultado.total_deducciones,
            total_neto=resultado.neto_pagar,
            dias_trabajados=entrada.dias_trabajados,
            horas_extras=q(entrada.horas_extra_diurnas + entrada.horas_extra_nocturnas),
            estado="CALCULADA",
            fecha_calculo=ahora,
        )
        detalles = []
        for codigo, (_n, _t, _c, campo) in CONCEPTOS_LOTTT.items():
            monto = getattr(resultado, campo)
            if monto == 0 and codigo != "SUELDO":
                continue  # solo líneas con monto (el sueldo siempre se registra)
            detalles.append(
                DetalleNomina(
                    id_nomina=nomina,
                    id_concepto_nomina=conceptos[codigo],
                    cantidad=Decimal("1"),
                    valor_unitario=monto,
                    valor_total=monto,
                )
            )
        DetalleNomina.objects.bulk_create(detalles)

        total_devengado += resultado.total_asignaciones
        total_deducciones += resultado.total_deducciones
        total_neto += resultado.neto_pagar

    proceso.total_empleados = len(empleados)
    proceso.total_devengado = total_devengado
    proceso.total_deducciones = total_deducciones
    proceso.total_neto = total_neto
    proceso.estado = "COMPLETADO"
    proceso.fecha_proceso = ahora
    proceso.save()

    # R-CODE-11: asiento contable en la MISMA transacción. Si la empresa exige
    # contabilidad y falta el mapeo NOMINA, AsientoError revienta y revierte todo.
    asiento, advertencia = generar_asiento_o_fallar(
        "NOMINA", proceso, empresa, monto=total_neto, usuario=usuario
    )

    logger.info(
        "nomina.procesar | proceso=%s | empresa=%s | empleados=%d | neto=%s | asiento=%s",
        proceso.numero_proceso, empresa.pk, len(empleados), total_neto,
        getattr(asiento, "numero_asiento", None),
    )
    return proceso, asiento, advertencia
