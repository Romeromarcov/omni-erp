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

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

CERO = Decimal("0")
#: Tolerancia al comparar el total del cliente con el del servidor.
EPSILON_TOTAL = Decimal("0.01")
#: Precisión de los importes de línea (DetalleNotaVenta.subtotal es Decimal(18,4)).
CUANTOS = Decimal("0.0001")


class VentaPosError(Exception):
    """Error de validación de la venta POS (el endpoint lo traduce a 4xx)."""


def _decimal(valor, campo: str) -> Decimal:
    if valor is None or valor == "":
        raise VentaPosError(f"Falta el valor numérico de '{campo}'.")
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise VentaPosError(f"Valor decimal inválido en '{campo}': {valor!r}.")


def _obligatorio(datos: dict, campo: str):
    valor = datos.get(campo)
    if not valor:
        raise VentaPosError(f"Falta el campo obligatorio '{campo}'.")
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
    from apps.crm.models import Cliente
    from apps.finanzas.models import Caja, CuentaBancariaEmpresa, MetodoPago, Moneda, Pago
    from apps.finanzas.services import registrar_efectos_pago
    from apps.inventario.models import Producto
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

    def _tenant_get(modelo, valor, campo, empresa_field="id_empresa"):
        if not valor:
            raise VentaPosError(f"Falta el campo obligatorio '{campo}'.")
        try:
            return modelo.objects.get(**{"pk": valor, empresa_field: empresa})
        except modelo.DoesNotExist:
            raise VentaPosError(f"'{campo}' no encontrado en esta empresa.")

    cliente = _tenant_get(Cliente, datos.get("id_cliente"), "id_cliente")
    almacen = _tenant_get(Almacen, datos.get("id_almacen"), "id_almacen")

    numero_nota = str(datos.get("numero_nota") or f"POS-{client_uuid or ''}").strip()[:50]
    if not numero_nota or numero_nota == "POS-":
        raise VentaPosError("No se pudo determinar 'numero_nota' (falta 'client_uuid').")

    documento_json = None
    if client_uuid:
        documento_json = {"client_uuid": str(client_uuid)}
        if datos.get("fecha_local"):
            documento_json["fecha_local"] = str(datos["fecha_local"])

    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_nota=numero_nota,
        fecha_nota=timezone.localdate(),
        estado="BORRADOR",
        documento_json=documento_json,
    )

    # --- Detalles: el servidor recalcula el subtotal de cada línea (R-CODE-4) ---
    total_servidor = CERO
    for i, det in enumerate(detalles_in):
        if not isinstance(det, dict):
            raise VentaPosError(f"'detalles[{i}]' debe ser un objeto.")
        producto = _tenant_get(Producto, det.get("id_producto"), f"detalles[{i}].id_producto")
        cantidad = _decimal(det.get("cantidad"), f"detalles[{i}].cantidad")
        precio = _decimal(det.get("precio_unitario"), f"detalles[{i}].precio_unitario")
        if cantidad <= CERO:
            raise VentaPosError(f"La cantidad de 'detalles[{i}]' debe ser mayor que 0.")
        if precio < CERO:
            raise VentaPosError(f"El precio de 'detalles[{i}]' no puede ser negativo.")
        subtotal = (cantidad * precio).quantize(CUANTOS)
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
                f"por el servidor ({total_servidor}); la venta requiere revisión."
            )

    # --- Entrega: despacho de stock + CxC del flujo + asiento (lógica existente) ---
    try:
        resultado = confirmar_nota_venta(nota, almacen, usuario)
    except VentaError as exc:
        raise VentaPosError(str(exc)) from exc

    # --- Pagos: ligados a la nota; efectos financieros con la lógica existente ---
    pagos_creados = []
    for i, p in enumerate(pagos_in):
        if not isinstance(p, dict):
            raise VentaPosError(f"'pagos[{i}]' debe ser un objeto.")
        try:
            metodo = MetodoPago.objects.get(pk=_obligatorio(p, "id_metodo_pago"))
        except MetodoPago.DoesNotExist:
            raise VentaPosError(f"'pagos[{i}].id_metodo_pago' no existe.")
        try:
            moneda = Moneda.objects.get(pk=_obligatorio(p, "id_moneda"))
        except Moneda.DoesNotExist:
            raise VentaPosError(f"'pagos[{i}].id_moneda' no existe.")
        monto = _decimal(p.get("monto"), f"pagos[{i}].monto")
        if monto <= CERO:
            raise VentaPosError(f"El monto de 'pagos[{i}]' debe ser mayor que 0.")
        tasa = _decimal(p.get("tasa", "1"), f"pagos[{i}].tasa")

        caja_virtual = None
        if p.get("id_caja_virtual"):
            try:
                caja_virtual = Caja.objects.get(pk=p["id_caja_virtual"], empresa=empresa)
            except Caja.DoesNotExist:
                raise VentaPosError(
                    f"'pagos[{i}].id_caja_virtual' no encontrada en esta empresa."
                )
        cuenta_bancaria = None
        if p.get("id_cuenta_bancaria"):
            try:
                cuenta_bancaria = CuentaBancariaEmpresa.objects.get(
                    pk=p["id_cuenta_bancaria"], id_empresa=empresa
                )
            except CuentaBancariaEmpresa.DoesNotExist:
                raise VentaPosError(
                    f"'pagos[{i}].id_cuenta_bancaria' no encontrada en esta empresa."
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
            id_caja_virtual=caja_virtual,
            id_cuenta_bancaria=cuenta_bancaria,
            referencia=p.get("referencia") or None,
            id_usuario_registro=usuario,
        )
        registrar_efectos_pago(pago)
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
        "pagos": [str(p.id_pago) for p in pagos_creados],
    }
