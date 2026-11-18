"""Servicios transaccionales multi-tenant de ingesta y consolidación de extractos bancarios."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, models, transaction

from .clasificacion import clasificar_linea
from .lector_hojas import TAMANO_MAXIMO_ARCHIVO
from .modelos_canonicos import (
    CERO,
    EstadoCuentaCanonico,
    ExtractoBancarioError,
    LineaExtractoCanonica,
    ResultadoValidacion,
    validar_estado,
)
from .parsers import extraer_sufijo_cuenta, inferir_formato_banco, parsear_extracto
from .saldos import ConsolidadoExtractos, CorteExtracto, consolidar_cortes

if TYPE_CHECKING:
    from apps.core.models import Empresa, Usuarios
    from apps.finanzas.models import CuentaBancariaEmpresa
    from apps.tesoreria.models import ExtractoBancarioArchivo


@dataclass(frozen=True)
class LineaClasificada:
    linea: LineaExtractoCanonica
    categoria: str
    regla: str


@dataclass
class ExtractoPreparado:
    sha256: str
    nombre_archivo: str
    tamano_bytes: int
    estado: EstadoCuentaCanonico
    validacion: ResultadoValidacion
    lineas: list[LineaClasificada]

    @property
    def observaciones(self) -> str:
        partes = list(self.validacion.saltos)
        if self.validacion.duplicados:
            partes.append(f"{len(self.validacion.duplicados)} huella(s) repetida(s) en el archivo")
        if self.estado.saldo_inicial_derivado:
            partes.append("saldo inicial derivado del 1er movimiento")
        partes.extend(self.estado.avisos)
        return "; ".join(partes)


def preparar_extracto(
    contenido: bytes,
    nombre_archivo: str,
    *,
    formato_banco: str,
    cuenta_clave: str,
    moneda: str = "VES",
    cuenta_sufijo: str | None = None,
) -> ExtractoPreparado:
    """Valida tamaño, parsea, verifica cadena de saldos y clasifica líneas (puro, sin BD)."""
    nombre_limpio = (nombre_archivo or "extracto").replace("\x00", "")
    if not contenido:
        raise ExtractoBancarioError("El archivo de extracto está vacío.")
    if len(contenido) > TAMANO_MAXIMO_ARCHIVO:
        raise ExtractoBancarioError(
            f"El archivo excede el tamaño máximo permitido de {TAMANO_MAXIMO_ARCHIVO // (1024 * 1024)} MB."
        )
    estado = parsear_extracto(
        contenido,
        nombre_limpio,
        formato_banco,
        cuenta_clave=cuenta_clave,
        moneda=moneda,
        cuenta_sufijo=cuenta_sufijo,
    )
    if not estado.movimientos:
        raise ExtractoBancarioError(f"{nombre_limpio}: no se encontró ningún movimiento bancario.")

    lineas = [LineaClasificada(m, *clasificar_linea(m)) for m in estado.movimientos]
    return ExtractoPreparado(
        sha256=hashlib.sha256(contenido).hexdigest(),
        nombre_archivo=nombre_limpio,
        tamano_bytes=len(contenido),
        estado=estado,
        validacion=validar_estado(estado),
        lineas=lineas,
    )


@dataclass
class ResultadoImportacionExtracto:
    archivo: "ExtractoBancarioArchivo"
    ya_existia_archivo: bool
    lineas_nuevas: int
    lineas_duplicadas: int
    cuadra: bool
    saltos: list[str]
    avisos: list[str]


def importar_extracto_bancario(
    *,
    empresa: "Empresa",
    cuenta_bancaria: "CuentaBancariaEmpresa",
    contenido: bytes,
    nombre_archivo: str,
    formato_banco: str | None = None,
    usuario: "Usuarios | None" = None,
) -> ResultadoImportacionExtracto:
    """Importa un extracto bancario validado y deduplicado para una cuenta de la empresa.

    - Idempotente por archivo: re-subir los mismos bytes para la misma cuenta devuelve
      ``ya_existia_archivo=True`` sin duplicar registros.
    - Idempotente por línea: un corte solapado solo inserta las ``huella``s nuevas y
      contabiliza las ya existentes en ``lineas_duplicadas``.
    - Persiste los cortes con descuadre marcados ``cuadra=False`` para visibilizar
      huecos o filas faltantes en auditoría de tesorería.
    """
    from apps.finanzas.models import CuentaBancariaEmpresa
    from apps.tesoreria.models import ExtractoBancarioArchivo, MovimientoBancario

    if str(cuenta_bancaria.id_empresa_id) != str(empresa.pk):
        raise ExtractoBancarioError("La cuenta bancaria no pertenece a la empresa activa.")

    nombre_limpio = ((nombre_archivo or "extracto").replace("\x00", "").strip() or "extracto")[:255]
    moneda_iso = cuenta_bancaria.id_moneda.codigo_iso.strip().upper()
    formato = (formato_banco or "").replace("\x00", "").strip().upper() or inferir_formato_banco(
        cuenta_bancaria.nombre_banco
    )
    sufijo = extraer_sufijo_cuenta(cuenta_bancaria.numero_cuenta)
    preparado = preparar_extracto(
        contenido,
        nombre_limpio,
        formato_banco=formato,
        cuenta_clave=str(cuenta_bancaria.pk),
        moneda=moneda_iso,
        cuenta_sufijo=sufijo,
    )

    fechas = [lc.linea.fecha for lc in preparado.lineas]
    fecha_desde = min(fechas) if fechas else None
    fecha_hasta = max(fechas) if fechas else None
    saldo_cierre = (
        preparado.estado.saldo_final
        if preparado.estado.saldo_final is not None
        else preparado.validacion.saldo_final_calculado
    )

    with transaction.atomic():
        # Serializa importaciones/desactivaciones concurrentes sobre la misma cuenta bancaria
        # evitando carreras tanto en sha256 como en huellas solapadas durante bulk_create.
        CuentaBancariaEmpresa.objects.select_for_update().get(pk=cuenta_bancaria.pk)

        existente = (
            ExtractoBancarioArchivo.objects.select_for_update()
            .filter(
                id_empresa=empresa,
                id_cuenta_bancaria=cuenta_bancaria,
                sha256=preparado.sha256,
                activo=True,
            )
            .first()
        )
        if existente is not None:
            return ResultadoImportacionExtracto(
                archivo=existente,
                ya_existia_archivo=True,
                lineas_nuevas=0,
                lineas_duplicadas=preparado.validacion.n_movimientos,
                cuadra=existente.cuadra,
                saltos=preparado.validacion.saltos,
                avisos=preparado.estado.avisos,
            )

        try:
            with transaction.atomic():
                archivo_obj = ExtractoBancarioArchivo.objects.create(
                    id_empresa=empresa,
                    id_cuenta_bancaria=cuenta_bancaria,
                    formato_banco=preparado.estado.formato_banco,
                    nombre_archivo=nombre_limpio,
                    sha256=preparado.sha256,
                    tamano_bytes=preparado.tamano_bytes,
                    moneda=moneda_iso,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    saldo_inicial=preparado.estado.saldo_inicial,
                    saldo_final=saldo_cierre,
                    total_debitos=preparado.validacion.total_debitos,
                    total_creditos=preparado.validacion.total_creditos,
                    total_lineas=preparado.validacion.n_movimientos,
                    cuadra=preparado.validacion.ok,
                    observaciones=preparado.observaciones,
                    subido_por=usuario if (usuario and usuario.is_authenticated) else None,
                )
        except IntegrityError:
            # Savepoint aislado evita abortar la transacción externa en PostgreSQL.
            ganador = ExtractoBancarioArchivo.objects.get(
                id_empresa=empresa,
                id_cuenta_bancaria=cuenta_bancaria,
                sha256=preparado.sha256,
                activo=True,
            )
            return ResultadoImportacionExtracto(
                archivo=ganador,
                ya_existia_archivo=True,
                lineas_nuevas=0,
                lineas_duplicadas=preparado.validacion.n_movimientos,
                cuadra=ganador.cuadra,
                saltos=preparado.validacion.saltos,
                avisos=preparado.estado.avisos,
            )

        huellas_candidatas = {lc.linea.huella for lc in preparado.lineas}
        huellas_existentes = set(
            MovimientoBancario.objects.filter(
                id_empresa=empresa,
                id_cuenta_bancaria=cuenta_bancaria,
                huella__in=huellas_candidatas,
                activo=True,
            ).values_list("huella", flat=True)
        )

        nuevas = 0
        duplicadas = 0
        vistas_en_lote: set[str] = set()
        objetos_nuevos: list[MovimientoBancario] = []

        for lc in preparado.lineas:
            h = lc.linea.huella
            if h in huellas_existentes or h in vistas_en_lote:
                duplicadas += 1
                continue
            vistas_en_lote.add(h)
            objetos_nuevos.append(
                MovimientoBancario(
                    id_empresa=empresa,
                    id_cuenta_bancaria=cuenta_bancaria,
                    id_archivo_extracto=archivo_obj,
                    fecha_mov=lc.linea.fecha,
                    descripcion=(lc.linea.descripcion or "Sin descripción").replace("\x00", "")[:300],
                    tipo=lc.linea.tipo_movimiento,
                    monto=lc.linea.monto_absoluto,
                    referencia=(lc.linea.referencia or "").replace("\x00", "")[:100],
                    estado="PENDIENTE",
                    origen="EXTRACTO",
                    huella=h,
                    saldo_posterior=lc.linea.saldo,
                    orden_en_archivo=lc.linea.orden,
                    codigo_operacion=(lc.linea.codigo or "").replace("\x00", "")[:30],
                    correlativo=(lc.linea.correlativo or "").replace("\x00", "")[:50],
                    categoria_clasificacion=lc.categoria[:50],
                    regla_clasificacion=lc.regla[:50],
                )
            )
            nuevas += 1

        if objetos_nuevos:
            MovimientoBancario.objects.bulk_create(objetos_nuevos)

        archivo_obj.lineas_nuevas = nuevas
        archivo_obj.lineas_duplicadas = duplicadas
        archivo_obj.save(update_fields=["lineas_nuevas", "lineas_duplicadas"])

    return ResultadoImportacionExtracto(
        archivo=archivo_obj,
        ya_existia_archivo=False,
        lineas_nuevas=nuevas,
        lineas_duplicadas=duplicadas,
        cuadra=archivo_obj.cuadra,
        saltos=preparado.validacion.saltos,
        avisos=preparado.estado.avisos,
    )


def obtener_tasa_usd_ves(empresa: "Empresa", fecha: date) -> Decimal | None:
    """Obtiene la tasa USD→VES aplicable a la empresa en o antes de ``fecha``."""
    from apps.finanzas.models import TasaCambio

    filtro_tenant = models.Q(id_empresa=empresa) | models.Q(id_empresa__isnull=True)
    orden_precedencia = (
        "-fecha_tasa",
        models.Case(
            models.When(id_empresa=empresa, then=models.Value(0)),
            default=models.Value(1),
            output_field=models.IntegerField(),
        ),
        models.Case(
            models.When(tipo_tasa="OFICIAL_BCV", then=models.Value(0)),
            default=models.Value(1),
            output_field=models.IntegerField(),
        ),
        "-hora_tasa",
    )
    directa = (
        TasaCambio.objects.filter(
            filtro_tenant,
            id_moneda_origen__codigo_iso__in=("USD", "USDT"),
            id_moneda_destino__codigo_iso="VES",
            fecha_tasa__lte=fecha,
        )
        .order_by(*orden_precedencia)
        .first()
    )
    if directa and Decimal(str(directa.valor_tasa)) > CERO:
        return Decimal(str(directa.valor_tasa))

    inversa = (
        TasaCambio.objects.filter(
            filtro_tenant,
            id_moneda_origen__codigo_iso="VES",
            id_moneda_destino__codigo_iso__in=("USD", "USDT"),
            fecha_tasa__lte=fecha,
        )
        .order_by(*orden_precedencia)
        .first()
    )
    if inversa and Decimal(str(inversa.valor_tasa)) > CERO:
        return (Decimal("1") / Decimal(str(inversa.valor_tasa))).quantize(Decimal("0.00000001"))

    return None


def consolidar_saldos_extractos(
    empresa: "Empresa",
    *,
    cuenta_id: str | None = None,
) -> ConsolidadoExtractos:
    """Consolida los saldos bancarios de todos los extractos activos del tenant."""
    from apps.tesoreria.models import ExtractoBancarioArchivo

    qs = (
        ExtractoBancarioArchivo.objects.filter(id_empresa=empresa, activo=True)
        .select_related("id_cuenta_bancaria")
        .order_by("fecha_desde", "fecha_creacion")
    )
    if cuenta_id:
        qs = qs.filter(id_cuenta_bancaria_id=uuid.UUID(str(cuenta_id)))

    cortes = [
        CorteExtracto(
            archivo_id=str(a.id),
            cuenta_id=str(a.id_cuenta_bancaria_id),
            nombre_banco=a.id_cuenta_bancaria.nombre_banco,
            numero_cuenta=a.id_cuenta_bancaria.numero_cuenta,
            moneda=a.moneda,
            nombre_archivo=a.nombre_archivo,
            fecha_desde=a.fecha_desde,
            fecha_hasta=a.fecha_hasta,
            saldo_inicial=a.saldo_inicial,
            saldo_final=a.saldo_final,
            cuadra=a.cuadra,
            cargado_en=a.fecha_creacion,
        )
        for a in qs
    ]

    cache_tasas: dict[date, Decimal | None] = {}

    def _resolver(f: date) -> Decimal | None:
        if f not in cache_tasas:
            cache_tasas[f] = obtener_tasa_usd_ves(empresa, f)
        return cache_tasas[f]

    return consolidar_cortes(cortes, _resolver)


def serializar_consolidado(cons: ConsolidadoExtractos) -> dict[str, Any]:
    """Serializa ``ConsolidadoExtractos`` con decimales exactos como strings."""
    return {
        "total_usd": f"{cons.total_usd:.2f}",
        "total_ves": f"{cons.total_ves:.2f}",
        "fechas_de_corte": [d.isoformat() for d in cons.fechas_de_corte],
        "cuentas_sin_tasa": cons.cuentas_sin_tasa,
        "cuentas": [
            {
                "cuenta_id": c.cuenta_id,
                "nombre_banco": c.nombre_banco,
                "numero_cuenta": c.numero_cuenta,
                "moneda": c.moneda,
                "fecha_corte": c.fecha_corte.isoformat() if c.fecha_corte else None,
                "saldo": f"{c.saldo:.2f}" if c.saldo is not None else None,
                "tasa_usd_ves": str(c.tasa_usd_ves) if c.tasa_usd_ves is not None else None,
                "saldo_usd": f"{c.saldo_usd:.2f}" if c.saldo_usd is not None else None,
                "saldo_ves": f"{c.saldo_ves:.2f}" if c.saldo_ves is not None else None,
                "n_cortes": c.n_cortes,
                "cortes_sin_cuadrar": c.cortes_sin_cuadrar,
                "alertas": c.alertas,
            }
            for c in cons.cuentas
        ],
    }


def desactivar_extracto_bancario(archivo: "ExtractoBancarioArchivo") -> int:
    """Desactiva lógicamente (R-CODE-6) un extracto y sus movimientos aún pendientes.

    Rechaza con ``ExtractoBancarioError`` si el extracto ya posee movimientos
    conciliados o propuestas de pre-conciliación decididas por un usuario para
    preservar la trazabilidad contable, bloqueando la cuenta, el corte y sus
    movimientos activos con ``select_for_update()``.
    """
    from apps.finanzas.models import CuentaBancariaEmpresa
    from apps.tesoreria.models import (
        ConciliacionBancaria,
        ExtractoBancarioArchivo,
        PropuestaConciliacionBancaria,
    )

    with transaction.atomic():
        CuentaBancariaEmpresa.objects.select_for_update().get(pk=archivo.id_cuenta_bancaria_id)
        archivo_locked = ExtractoBancarioArchivo.objects.select_for_update().get(pk=archivo.pk)
        movimientos_activos = list(archivo_locked.movimientos.select_for_update().filter(activo=True))
        if any(m.estado == "CONCILIADO" for m in movimientos_activos):
            raise ExtractoBancarioError("No se puede desactivar un extracto que ya tiene movimientos conciliados.")
        fechas_mov = [m.fecha_mov for m in movimientos_activos]
        f_min = min(fechas_mov) if fechas_mov else archivo_locked.fecha_desde
        f_max = max(fechas_mov) if fechas_mov else archivo_locked.fecha_hasta
        if f_min is not None and f_max is not None:
            periodo_cerrado = ConciliacionBancaria.objects.filter(
                id_empresa_id=archivo_locked.id_empresa_id,
                id_cuenta_bancaria_id=archivo_locked.id_cuenta_bancaria_id,
                periodo_inicio__lte=f_max,
                periodo_fin__gte=f_min,
                estado="CERRADA",
            ).exists()
            if periodo_cerrado:
                raise ExtractoBancarioError(
                    "No se puede desactivar un extracto dentro de un período de conciliación cerrado."
                )
        ids_activos = [m.pk for m in movimientos_activos]
        if ids_activos:
            props_activas = list(
                PropuestaConciliacionBancaria.objects.select_for_update().filter(
                    id_empresa_id=archivo_locked.id_empresa_id,
                    id_movimiento_bancario_id__in=ids_activos,
                    activo=True,
                )
            )
            if any(p.estado != "PENDIENTE" for p in props_activas):
                raise ExtractoBancarioError(
                    "No se puede desactivar un extracto con decisiones humanas de pre-conciliación registradas."
                )
            if props_activas:
                PropuestaConciliacionBancaria.objects.filter(pk__in=[p.pk for p in props_activas]).update(activo=False)
        desactivados = archivo_locked.movimientos.filter(pk__in=ids_activos).update(activo=False) if ids_activos else 0
        archivo_locked.activo = False
        archivo_locked.save(update_fields=["activo"])
        archivo.activo = False
    return int(desactivados)
