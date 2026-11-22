"""Venta POS offline atómica — ADR-012.

Crea **nota de venta + detalles + entrega (despacho/CxC/asiento) + pagos** como
UNA unidad atómica, reutilizando los services de dinero existentes
(``confirmar_nota_venta``, ``registrar_efectos_pago``) sin reimplementar lógica
fiscal/contable (R-PROC-2).

Garantías:
- **Atómico** (``@transaction.atomic``): si cualquier paso falla, no queda ni la
  nota, ni el despacho, ni los pagos (nada de ventas huérfanas — ADR-012).
- **Multi-tenant** (R-CODE-1): la empresa se inyecta del usuario; toda FK del
  payload se valida contra esa empresa (anti-IDOR).
- **Decimal** en todo el dinero (R-CODE-4); el servidor recalcula los subtotales
  y verifica el total del cliente de forma defensiva (el cliente no es la
  autoridad fiscal).
- **Idempotencia**: la provee el endpoint vía ``Idempotency-Key`` (= client_uuid).
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .registry import SYNC_ENTITIES, SyncEntity

CERO = Decimal("0")
#: Tolerancia al comparar el total del cliente con el del servidor.
EPSILON_TOTAL = Decimal("0.01")
#: Precisión de los importes de línea (DetalleNotaVenta.subtotal es Decimal(18,4)).
CUANTOS = Decimal("0.0001")
_TRUTHY_PARAM = frozenset({"true", "1", "si", "yes"})


class VentaPosError(Exception):
    """Error de validación de la venta POS (el endpoint lo traduce a 4xx)."""

    def __init__(self, mensaje: str, *, codigo: str | None = None):
        super().__init__(mensaje)
        self.codigo = codigo


def _permitir_stock_negativo_pos(empresa) -> bool:
    """Lee ``permitir_stock_negativo_pos`` de ParametroSistema (override empresa > global, cacheado)."""
    from apps.configuracion_motor.services import obtener_parametro

    valor = obtener_parametro("permitir_stock_negativo_pos", empresa=empresa, incluir_global=True)
    if valor is None:
        return False
    return valor.lower() in _TRUTHY_PARAM


def _decimal(valor, campo: str) -> Decimal:
    if valor is None or valor == "":
        raise VentaPosError(f"Falta el valor numérico de '{campo}'.", codigo="REQUIERE_REVISION")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise VentaPosError(f"Valor decimal inválido en '{campo}': {valor!r}.", codigo="REQUIERE_REVISION")
    if not d.is_finite():
        raise VentaPosError(f"Valor decimal no finito en '{campo}': {valor!r}.", codigo="REQUIERE_REVISION")
    return d


def _obligatorio(datos: dict, campo: str):
    valor = datos.get(campo)
    if not valor:
        raise VentaPosError(f"Falta el campo obligatorio '{campo}'.", codigo="REQUIERE_REVISION")
    return valor


@transaction.atomic
def crear_venta_pos_offline(empresa, usuario, datos: dict) -> dict:
    """Crea una venta POS completa de forma atómica. Ver módulo para garantías.

    Args:
        empresa: tenant dueño de la venta (inyectado del usuario, nunca del payload).
        usuario: usuario autenticado que registra la venta.
        datos:   sobre ``VentaOffline`` (ADR-012): client_uuid, id_cliente,
                 id_almacen, detalles[], pagos[], totales_cliente.

    Returns:
        dict JSON-safe con id_nota_venta del servidor, número, total, CxC y pagos.

    Raises:
        VentaPosError: ante cualquier dato inválido (la transacción revierte).
    """
    from apps.almacenes.models import Almacen
    from apps.core.models import Sucursal
    from apps.crm.models import Cliente
    from apps.finanzas.models import Caja, CajaFisica, CuentaBancariaEmpresa, MetodoPago, Moneda, Pago
    from apps.finanzas.services import TasaCambioError, registrar_efectos_pago
    from apps.inventario.models import Producto, StockActual
    from apps.inventario.services import StockInsuficienteError
    from apps.ventas.models import DetalleNotaVenta, NotaVenta
    from apps.ventas.services import VentaError, confirmar_nota_venta

    if not isinstance(datos, dict):
        raise VentaPosError("El cuerpo de la venta debe ser un objeto JSON.")

    detalles_in = datos.get("detalles")
    if not isinstance(detalles_in, list) or not detalles_in:
        raise VentaPosError("La venta debe incluir al menos una línea en 'detalles'.")
    pagos_in = datos.get("pagos") or []
    if not isinstance(pagos_in, list):
        raise VentaPosError("'pagos' debe ser una lista.")

    client_uuid = datos.get("client_uuid")

    def _tenant_get(modelo, valor, campo, empresa_field="id_empresa", *, codigo: str | None = None):
        if not valor:
            raise VentaPosError(f"Falta el campo obligatorio '{campo}'.", codigo=codigo)
        try:
            return modelo.objects.get(**{"pk": valor, empresa_field: empresa})
        except (modelo.DoesNotExist, DjangoValidationError, ValueError):
            raise VentaPosError(f"'{campo}' no encontrado en esta empresa.", codigo=codigo)

    cliente = _tenant_get(Cliente, datos.get("id_cliente"), "id_cliente", codigo="REQUIERE_REVISION")
    if datos.get("id_almacen"):
        almacen = _tenant_get(Almacen, datos.get("id_almacen"), "id_almacen", codigo="REQUIERE_REVISION")
    elif datos.get("id_sucursal"):
        sucursal = _tenant_get(Sucursal, datos.get("id_sucursal"), "id_sucursal", codigo="REQUIERE_REVISION")
        almacen = (
            Almacen.objects.filter(id_empresa=empresa, id_sucursal=sucursal, activo=True)
            .order_by("fecha_creacion", "id_almacen")
            .first()
        )
        if almacen is None:
            almacen = (
                Almacen.objects.filter(id_empresa=empresa, id_sucursal__isnull=True, activo=True)
                .order_by("fecha_creacion", "id_almacen")
                .first()
            )
        if almacen is None:
            raise VentaPosError("Falta el campo obligatorio 'id_almacen'.", codigo="REQUIERE_REVISION")
    else:
        raise VentaPosError("Falta el campo obligatorio 'id_almacen'.", codigo="REQUIERE_REVISION")

    caja_fisica_envelope = None
    if datos.get("id_caja"):
        try:
            caja_encontrada = CajaFisica.objects.filter(pk=datos["id_caja"]).first()
        except (DjangoValidationError, ValueError):
            caja_encontrada = None
        if caja_encontrada is not None:
            if caja_encontrada.empresa_id != empresa.pk:
                raise VentaPosError("'id_caja' no encontrada en esta empresa.", codigo="REQUIERE_REVISION")
            caja_fisica_envelope = caja_encontrada

    numero_nota = str(datos.get("numero_nota") or f"POS-{client_uuid or ''}").strip()[:50]
    if not numero_nota or numero_nota == "POS-":
        raise VentaPosError("No se pudo determinar 'numero_nota' (falta 'client_uuid').")

    documento_json = None
    if client_uuid:
        documento_json = {"client_uuid": str(client_uuid)}
        if datos.get("fecha_local"):
            documento_json["fecha_local"] = str(datos["fecha_local"])

    try:
        with transaction.atomic():
            nota = NotaVenta.objects.create(
                id_empresa=empresa,
                id_cliente=cliente,
                numero_nota=numero_nota,
                fecha_nota=timezone.localdate(),
                estado="BORRADOR",
                documento_json=documento_json,
            )
    except IntegrityError as exc:
        raise VentaPosError(
            f"Ya existe una nota de venta con el número '{numero_nota}' en esta empresa.",
            codigo="REQUIERE_REVISION",
        ) from exc

    # --- Detalles: el servidor recalcula el subtotal de cada línea (R-CODE-4) ---
    total_servidor = CERO
    for i, det in enumerate(detalles_in):
        if not isinstance(det, dict):
            raise VentaPosError(f"'detalles[{i}]' debe ser un objeto.", codigo="REQUIERE_REVISION")
        producto = _tenant_get(
            Producto,
            det.get("id_producto"),
            f"detalles[{i}].id_producto",
            codigo="REQUIERE_REVISION",
        )
        cantidad = _decimal(det.get("cantidad"), f"detalles[{i}].cantidad")
        precio = _decimal(det.get("precio_unitario"), f"detalles[{i}].precio_unitario")
        raw_desc = det.get("descuento_porcentaje")
        descuento_pct = _decimal("0" if raw_desc is None else raw_desc, f"detalles[{i}].descuento_porcentaje")
        if cantidad <= CERO:
            raise VentaPosError(f"La cantidad de 'detalles[{i}]' debe ser mayor que 0.", codigo="REQUIERE_REVISION")
        if precio < CERO:
            raise VentaPosError(f"El precio de 'detalles[{i}]' no puede ser negativo.", codigo="REQUIERE_REVISION")
        if descuento_pct < CERO or descuento_pct > Decimal("100"):
            raise VentaPosError(
                f"El descuento de 'detalles[{i}]' debe estar entre 0 y 100.",
                codigo="REQUIERE_REVISION",
            )
        factor_descuento = Decimal("1") - (descuento_pct / Decimal("100"))
        subtotal = (cantidad * precio * factor_descuento).quantize(CUANTOS)
        DetalleNotaVenta.objects.create(
            id_nota_venta=nota,
            id_producto=producto,
            cantidad=cantidad,
            precio_unitario=precio,
            subtotal=subtotal,
        )
        total_servidor += subtotal

    # --- Verificación defensiva: el servidor manda en el dinero (ADR-012 §2) ---
    totales_cliente = datos.get("totales_cliente") or {}
    if isinstance(totales_cliente, dict) and totales_cliente.get("total") is not None:
        total_cliente = _decimal(totales_cliente.get("total"), "totales_cliente.total")
        if abs(total_cliente - total_servidor) > EPSILON_TOTAL:
            raise VentaPosError(
                f"El total del cliente ({total_cliente}) difiere del total calculado "
                f"por el servidor ({total_servidor}); la venta requiere revisión.",
                codigo="REQUIERE_REVISION",
            )

    # --- Entrega: despacho de stock + CxC del flujo + asiento (lógica existente) ---
    permitir_negativo = _permitir_stock_negativo_pos(empresa)
    try:
        resultado = confirmar_nota_venta(
            nota,
            almacen,
            usuario,
            permitir_stock_negativo=permitir_negativo,
        )
    except VentaError as exc:
        es_stock_insuficiente = isinstance(exc.__cause__, StockInsuficienteError) or (
            "stock insuficiente" in str(exc).lower()
        )
        raise VentaPosError(
            str(exc),
            codigo="REQUIERE_REVISION" if es_stock_insuficiente else None,
        ) from exc

    producto_ids = {m.id_producto_id for m in resultado.get("movimientos", [])}
    stocks_negativos = (
        list(
            StockActual.objects.filter(
                id_empresa=empresa,
                id_almacen=almacen,
                id_producto_id__in=producto_ids,
                id_variante__isnull=True,
                cantidad_disponible__lt=CERO,
            ).select_related("id_producto")
        )
        if permitir_negativo and producto_ids
        else []
    )
    alerta_stock_negativo = len(stocks_negativos) > 0
    productos_stock_negativo = [
        {
            "id_producto": str(s.id_producto_id),
            "nombre_producto": s.id_producto.nombre_producto,
            "cantidad_disponible": str(s.cantidad_disponible),
        }
        for s in stocks_negativos
    ]

    # --- Pagos: ligados a la nota; efectos financieros con la lógica existente ---
    pagos_creados = []
    for i, p in enumerate(pagos_in):
        if not isinstance(p, dict):
            raise VentaPosError(f"'pagos[{i}]' debe ser un objeto.", codigo="REQUIERE_REVISION")
        metodo_id = _obligatorio(p, "id_metodo_pago")
        try:
            metodo = MetodoPago.objects.filter(
                Q(empresa=empresa) | Q(empresa__isnull=True) | Q(es_publico=True) | Q(es_generico=True),
                activo=True,
            ).get(pk=metodo_id)
        except (MetodoPago.DoesNotExist, DjangoValidationError, ValueError):
            raise VentaPosError(
                f"'pagos[{i}].id_metodo_pago' no existe o no está disponible para esta empresa.",
                codigo="REQUIERE_REVISION",
            )
        moneda_id = _obligatorio(p, "id_moneda")
        try:
            moneda = Moneda.objects.filter(
                Q(empresa=empresa) | Q(empresa__isnull=True) | Q(es_publica=True) | Q(es_generica=True),
                activo=True,
            ).get(pk=moneda_id)
        except (Moneda.DoesNotExist, DjangoValidationError, ValueError):
            raise VentaPosError(
                f"'pagos[{i}].id_moneda' no existe o no está disponible para esta empresa.",
                codigo="REQUIERE_REVISION",
            )
        monto = _decimal(p.get("monto"), f"pagos[{i}].monto")
        if monto <= CERO:
            raise VentaPosError(f"El monto de 'pagos[{i}]' debe ser mayor que 0.", codigo="REQUIERE_REVISION")
        raw_tasa = p.get("tasa")
        tasa = _decimal("1" if raw_tasa is None else raw_tasa, f"pagos[{i}].tasa")
        if tasa <= CERO:
            raise VentaPosError(f"La tasa de 'pagos[{i}]' debe ser mayor que 0.", codigo="REQUIERE_REVISION")

        caja_fisica = None
        if p.get("id_caja_fisica"):
            try:
                caja_fisica = CajaFisica.objects.get(pk=p["id_caja_fisica"], empresa=empresa)
            except (CajaFisica.DoesNotExist, DjangoValidationError, ValueError):
                raise VentaPosError(
                    f"'pagos[{i}].id_caja_fisica' no encontrada en esta empresa.",
                    codigo="REQUIERE_REVISION",
                )
        elif caja_fisica_envelope is not None:
            caja_fisica = caja_fisica_envelope

        caja_virtual = None
        if p.get("id_caja_virtual"):
            try:
                caja_virtual = Caja.objects.get(pk=p["id_caja_virtual"], empresa=empresa)
            except (Caja.DoesNotExist, DjangoValidationError, ValueError):
                raise VentaPosError(
                    f"'pagos[{i}].id_caja_virtual' no encontrada en esta empresa.",
                    codigo="REQUIERE_REVISION",
                )
        cuenta_bancaria = None
        if p.get("id_cuenta_bancaria"):
            try:
                cuenta_bancaria = CuentaBancariaEmpresa.objects.get(pk=p["id_cuenta_bancaria"], id_empresa=empresa)
            except (CuentaBancariaEmpresa.DoesNotExist, DjangoValidationError, ValueError):
                raise VentaPosError(
                    f"'pagos[{i}].id_cuenta_bancaria' no encontrada en esta empresa.",
                    codigo="REQUIERE_REVISION",
                )

        pago = Pago.objects.create(
            id_empresa=empresa,
            tipo_operacion="INGRESO",
            tipo_documento="NOTA_VENTA",
            id_documento=nota.id_nota_venta,
            id_nota_venta=nota,
            fecha_pago=timezone.now(),
            monto=monto,
            id_moneda=moneda,
            tasa=tasa,
            id_metodo_pago=metodo,
            id_caja_fisica=caja_fisica,
            id_caja_virtual=caja_virtual,
            id_cuenta_bancaria=cuenta_bancaria,
            referencia=p.get("referencia") or None,
            id_usuario_registro=usuario,
        )
        try:
            registrar_efectos_pago(pago)
        except TasaCambioError as exc:
            raise VentaPosError(str(exc), codigo="REQUIERE_REVISION") from exc
        pagos_creados.append(pago)

    cxc = resultado.get("cxc")
    return {
        "id_nota_venta": str(nota.id_nota_venta),
        "client_uuid": str(client_uuid) if client_uuid else None,
        "numero_nota": nota.numero_nota,
        "estado": nota.estado,
        "total": str(total_servidor),
        "movimientos": len(resultado.get("movimientos", [])),
        "cxc_id": str(cxc.pk) if cxc else None,
        "asiento_generado": resultado.get("asiento") is not None,
        "alerta_stock_negativo": alerta_stock_negativo,
        "productos_stock_negativo": productos_stock_negativo,
        "pagos": [str(p.id_pago) for p in pagos_creados],
    }


# ── Push de ediciones con concurrencia optimista (CTF-008 Nivel 2) ────────────

MAX_MUTACIONES_LOTE = 100


class SyncPushError(Exception):
    """Error de validación/autorización en sync push de ediciones (404 / 422)."""

    def __init__(self, mensaje: str, *, codigo: str | None = None):
        super().__init__(mensaje)
        self.codigo = codigo


class SyncConflictError(Exception):
    """Conflicto de concurrencia optimista (409 CONFLICTO_VERSION)."""

    def __init__(
        self,
        mensaje: str,
        *,
        entity: str,
        record_id: str,
        registro_servidor: dict[str, Any],
        codigo: str = "CONFLICTO_VERSION",
        index: int | None = None,
    ):
        super().__init__(mensaje)
        self.entity = entity
        self.record_id = record_id
        self.registro_servidor = registro_servidor
        self.codigo = codigo
        self.index = index


def contiene_nul(valor: Any) -> bool:
    """Detecta bytes NUL (``\\x00``) recursivamente en strings, listas o dicts."""
    if isinstance(valor, str):
        return "\x00" in valor
    if isinstance(valor, dict):
        return any(contiene_nul(k) or contiene_nul(v) for k, v in valor.items())
    if isinstance(valor, (list, tuple)):
        return any(contiene_nul(item) for item in valor)
    return False


def _jsonificar_sync(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    if hasattr(valor, "pk"):
        return str(valor.pk)
    return valor


def _serializar_registro(instancia: models.Model, entidad: SyncEntity) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    for campo in entidad.fields:
        val = getattr(instancia, campo, None)
        resultado[campo] = _jsonificar_sync(val)
    return resultado


def _parse_uuid_estricto(raw: Any, campo: str) -> uuid.UUID:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise SyncPushError(f"El campo '{campo}' debe ser un UUID válido.", codigo="UUID_INVALIDO")
    try:
        return uuid.UUID(raw.strip())
    except (ValueError, TypeError) as exc:
        raise SyncPushError(f"El campo '{campo}' debe ser un UUID válido.", codigo="UUID_INVALIDO") from exc


def _parse_expected_timestamp(raw: Any) -> datetime.datetime:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise SyncPushError(
            "El campo 'expected_fecha_actualizacion' es requerido en formato ISO 8601.",
            codigo="VERSION_INVALIDA",
        )
    dt = parse_datetime(raw.strip())
    if dt is None:
        raise SyncPushError(
            "El campo 'expected_fecha_actualizacion' no es un timestamp ISO 8601 válido.",
            codigo="VERSION_INVALIDA",
        )
    if timezone.is_naive(dt):
        if settings.USE_TZ:
            dt = timezone.make_aware(dt, datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt


def _timestamps_coinciden(actual: Any, esperado: datetime.datetime) -> bool:
    if not isinstance(actual, datetime.datetime):
        return False
    actual_norm = (
        timezone.make_aware(actual, datetime.timezone.utc)
        if timezone.is_naive(actual)
        else actual.astimezone(datetime.timezone.utc)
    )
    return actual_norm == esperado


def _normalizar_campo(model_field: Any, valor: Any, nombre_campo: str) -> Any:
    if contiene_nul(valor):
        raise SyncPushError(f"El campo '{nombre_campo}' contiene caracteres inválidos.", codigo="CARACTER_INVALIDO")

    if valor is None:
        if getattr(model_field, "null", False):
            return None
        raise SyncPushError(f"El campo '{nombre_campo}' no admite valor nulo.", codigo="VALOR_INVALIDO")

    if isinstance(model_field, models.BooleanField):
        if not isinstance(valor, bool):
            raise SyncPushError(f"El campo '{nombre_campo}' debe ser booleano.", codigo="VALOR_INVALIDO")
        return valor

    if isinstance(model_field, models.DecimalField):
        if isinstance(valor, bool):
            raise SyncPushError(f"El campo '{nombre_campo}' debe ser numérico Decimal.", codigo="VALOR_INVALIDO")
        try:
            dec = Decimal(str(valor))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise SyncPushError(f"Valor decimal inválido en '{nombre_campo}'.", codigo="VALOR_INVALIDO") from exc
        if not dec.is_finite():
            raise SyncPushError(f"El campo '{nombre_campo}' debe ser finito.", codigo="VALOR_INVALIDO")
        return dec

    if isinstance(model_field, (models.CharField, models.TextField)):
        if not isinstance(valor, str):
            raise SyncPushError(f"El campo '{nombre_campo}' debe ser texto.", codigo="VALOR_INVALIDO")
        return valor.strip()

    return valor


@transaction.atomic
def aplicar_actualizacion_optimista(
    *,
    empresas,
    entity: Any,
    record_id: Any,
    expected_fecha_actualizacion: Any,
    cambios: Any,
) -> dict[str, Any]:
    """
    Aplica una edición optimista sobre una entidad whitelistada de ``SYNC_ENTITIES``.

    Bloquea la fila con ``select_for_update()`` filtrando estrictamente por
    ``empresas`` (R-CODE-1). Si ``fecha_actualizacion`` difiere de
    ``expected_fecha_actualizacion``, hace rollback y lanza ``SyncConflictError`` (409).
    """
    if not isinstance(entity, str) or entity not in SYNC_ENTITIES:
        raise SyncPushError(f"Entidad no sincronizable: {entity!r}.", codigo="ENTIDAD_INVALIDA")

    entidad = SYNC_ENTITIES[entity]
    if not entidad.editable_fields:
        raise SyncPushError(f"La entidad '{entity}' es de solo lectura en sync push.", codigo="ENTIDAD_NO_EDITABLE")

    pk_uuid = _parse_uuid_estricto(record_id, "id")
    expected_dt = _parse_expected_timestamp(expected_fecha_actualizacion)

    if not isinstance(cambios, dict) or not cambios:
        raise SyncPushError("El campo 'cambios' debe ser un objeto no vacío.", codigo="CAMBIOS_INVALIDOS")

    campos_permitidos = set(entidad.editable_fields)
    no_permitidos = sorted(set(cambios.keys()) - campos_permitidos)
    if no_permitidos:
        raise SyncPushError(
            f"Campos no editables para '{entity}': {', '.join(no_permitidos)}.",
            codigo="CAMPO_NO_EDITABLE",
        )

    modelo = django_apps.get_model(entidad.model_label)
    instancia = (
        modelo.objects.select_for_update()
        .filter(**{f"{entidad.empresa_field}__in": empresas, entidad.pk_field: pk_uuid})
        .first()
    )
    if instancia is None:
        raise SyncPushError("Registro no encontrado en la empresa.", codigo="NO_ENCONTRADO")

    actual_ts = getattr(instancia, entidad.delta_field, None)
    if not _timestamps_coinciden(actual_ts, expected_dt):
        raise SyncConflictError(
            "El registro fue modificado en el servidor desde la última sincronización.",
            entity=entity,
            record_id=str(pk_uuid),
            registro_servidor=_serializar_registro(instancia, entidad),
        )

    campos_actualizar: list[str] = []
    for campo, valor in cambios.items():
        model_field = instancia._meta.get_field(campo)
        normalizado = _normalizar_campo(model_field, valor, campo)
        setattr(instancia, campo, normalizado)
        campos_actualizar.append(campo)

    try:
        instancia.full_clean()
    except DjangoValidationError as exc:
        raise SyncPushError(
            f"Error de validación al actualizar '{entity}': {exc}", codigo="VALIDACION_FALLIDA"
        ) from exc

    if entidad.delta_field not in campos_actualizar:
        campos_actualizar.append(entidad.delta_field)
    instancia.save(update_fields=campos_actualizar)

    return {
        "entity": entity,
        "id": str(getattr(instancia, entidad.pk_field)),
        "server_time": timezone.now().isoformat(),
        "registro": _serializar_registro(instancia, entidad),
    }


@transaction.atomic
def aplicar_lote_actualizaciones_optimistas(*, empresas, mutaciones: Any) -> dict[str, Any]:
    """Ejecuta un lote atómico (1..100) de mutaciones optimistas; un 409 revierte todo."""
    if not isinstance(mutaciones, list) or not mutaciones:
        raise SyncPushError("'mutaciones' debe ser una lista no vacía.", codigo="LOTE_INVALIDO")
    if len(mutaciones) > MAX_MUTACIONES_LOTE:
        raise SyncPushError(
            f"El lote excede el máximo de {MAX_MUTACIONES_LOTE} mutaciones.",
            codigo="LOTE_EXCEDIDO",
        )

    resultados: list[dict[str, Any]] = []
    for idx, mut in enumerate(mutaciones):
        if not isinstance(mut, dict):
            raise SyncPushError(f"'mutaciones[{idx}]' debe ser un objeto JSON.", codigo="LOTE_INVALIDO")
        try:
            res = aplicar_actualizacion_optimista(
                empresas=empresas,
                entity=mut.get("entity"),
                record_id=mut.get("id"),
                expected_fecha_actualizacion=mut.get("expected_fecha_actualizacion"),
                cambios=mut.get("cambios"),
            )
        except SyncConflictError as exc:
            exc.index = idx
            raise
        resultados.append(res)

    return {
        "server_time": timezone.now().isoformat(),
        "count": len(resultados),
        "results": resultados,
    }
