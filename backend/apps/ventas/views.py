import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import models, transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

logger = logging.getLogger(__name__)


def _empresas(request):
    """Shortcut: devuelve empresas visibles para el usuario del request."""
    return get_empresas_visible(request.user)
from .models import (
    Cotizacion,
    DetalleCotizacion,
    DetalleDevolucionVenta,
    DetalleFacturaFiscal,
    DetalleNotaCreditoFiscal,
    DetalleNotaCreditoVenta,
    DetalleNotaVenta,
    DetallePedido,
    DetallePrecio,
    DevolucionVenta,
    FacturaFiscal,
    ListaPrecio,
    NotaCreditoFiscal,
    NotaCreditoVenta,
    NotaVenta,
    Pedido,
)
from .serializers import (
    CotizacionSerializer,
    DetalleCotizacionSerializer,
    DetalleDevolucionVentaSerializer,
    DetalleFacturaFiscalSerializer,
    DetalleNotaCreditoFiscalSerializer,
    DetalleNotaCreditoVentaSerializer,
    DetalleNotaVentaSerializer,
    DetallePedidoSerializer,
    DetallePrecioSerializer,
    DevolucionVentaSerializer,
    FacturaFiscalSerializer,
    ListaPrecioSerializer,
    NotaCreditoFiscalSerializer,
    NotaCreditoVentaSerializer,
    NotaVentaSerializer,
    PedidoSerializer,
)


def crear_transaccion_financiera_pago(pago, usuario):
    """
    Función helper para crear transacción financiera y movimiento de caja para un pago.
    Se puede llamar desde PagoPedidoViewSet.create o PedidoSerializer.create
    """
    from apps.finanzas.models import (
        Caja,
        CajaFisica,
        CuentaBancariaEmpresa,
        MetodoPago,
        Moneda,
        MovimientoCajaBanco,
        TransaccionFinanciera,
    )

    try:
        # Obtener información necesaria
        pedido = pago.id_pedido
        empresa = pedido.id_empresa

        logger.debug(
            f"Creando transacción financiera para pago: {pago.id_pago_pedido}, pedido: {pedido.numero_pedido}"
        )

        # Obtener monedas de la empresa
        try:
            moneda_base = empresa.id_moneda_base
            logger.debug(f"Moneda base encontrada: {moneda_base}")
        except Exception:
            # Fallback: buscar por código ISO USD
            try:
                moneda_base = Moneda.objects.get(codigo_iso="USD", empresa=empresa)
                logger.debug(f"Moneda base fallback USD encontrada: {moneda_base}")
            except Moneda.DoesNotExist:
                logger.debug(f"Moneda base fallback USD no encontrada, buscando primera moneda")
                moneda_base = Moneda.objects.filter(empresa=empresa).first()
                logger.debug(f"Primera moneda encontrada como base: {moneda_base}")

        try:
            moneda_pais = empresa.id_moneda_pais
            logger.debug(f"Moneda país encontrada: {moneda_pais}")
        except Exception:
            # Fallback: buscar por código ISO VES
            try:
                moneda_pais = Moneda.objects.get(codigo_iso="VES", empresa=empresa)
                logger.debug(f"Moneda país fallback VES encontrada: {moneda_pais}")
            except Moneda.DoesNotExist:
                logger.debug(f"Moneda país fallback VES no encontrada, buscando primera moneda")
                moneda_pais = Moneda.objects.filter(empresa=empresa).first()
                logger.debug(f"Primera moneda encontrada como país: {moneda_pais}")

        # Validar que tenemos las monedas necesarias
        if not moneda_base or not moneda_pais:
            logger.debug("ERROR: No se encontraron monedas base o país, no se crea transacción financiera")
            return

        # Obtener la moneda del pago
        try:
            # Buscar moneda por código ISO, puede ser de la empresa o genérica
            moneda_pago = (
                Moneda.objects.filter(codigo_iso=pago.moneda)
                .filter(models.Q(empresa=empresa) | models.Q(es_generica=True) | models.Q(es_publica=True))
                .first()
            )
            logger.debug(f"Moneda del pago encontrada: {moneda_pago}")
        except Exception as e:
            logger.warning("Error buscando moneda del pago '%s': %s", pago.moneda, e)
            moneda_pago = None

        if not moneda_pago:
            logger.debug(f"Moneda del pago {pago.moneda} no encontrada, usando moneda base")
            moneda_pago = moneda_base

        # Calcular montos en diferentes monedas usando las reglas correctas
        # Para monto_base: SI moneda_transacción = moneda_base → monto_base = monto_transacción
        #                  SI NO → monto_base = monto_transacción / tasa_cambio
        # Para monto_pais: SI moneda_transacción = moneda_pais → monto_pais = monto_transacción
        #                  SI NO → monto_pais = monto_transacción * tasa_cambio

        # Obtener tasas del sistema
        from datetime import date

        from apps.finanzas.models import TasaCambio

        hoy = date.today()

        # Calcular monto_base_empresa
        if moneda_pago == moneda_base:
            monto_base_empresa = pago.monto
        else:
            # Buscar tasa entre moneda_pago y moneda_base
            tasa_base = (
                TasaCambio.objects.filter(id_moneda_origen=moneda_pago, id_moneda_destino=moneda_base, fecha_tasa=hoy)
                .order_by("-fecha_tasa")
                .first()
            )
            if tasa_base:
                monto_base_empresa = Decimal(str(pago.monto)) / Decimal(str(tasa_base.valor_tasa))
            else:
                # Fallback: usar la tasa del pago
                tasa_pago = Decimal(str(pago.tasa)) if pago.tasa else Decimal("0")
                monto_base_empresa = Decimal(str(pago.monto)) / tasa_pago if tasa_pago > 0 else Decimal(str(pago.monto))

        # Calcular monto_moneda_pais
        if moneda_pago == moneda_pais:
            monto_moneda_pais = pago.monto
        else:
            # Buscar tasa entre moneda_pago y moneda_pais
            tasa_pais = (
                TasaCambio.objects.filter(id_moneda_origen=moneda_pago, id_moneda_destino=moneda_pais, fecha_tasa=hoy)
                .order_by("-fecha_tasa")
                .first()
            )
            if tasa_pais:
                monto_moneda_pais = Decimal(str(pago.monto)) * Decimal(str(tasa_pais.valor_tasa))
            else:
                # Fallback: usar la tasa del pago
                tasa_pago = Decimal(str(pago.tasa)) if pago.tasa else Decimal("0")
                monto_moneda_pais = Decimal(str(pago.monto)) * tasa_pago if tasa_pago > 0 else Decimal(str(pago.monto))

        logger.debug(f"Montos calculados correctamente:")
        logger.debug(f"  Monto transacción: {pago.monto} {moneda_pago}")
        logger.debug(f"  Monto base empresa: {monto_base_empresa} {moneda_base}")
        logger.debug(f"  Monto moneda país: {monto_moneda_pais} {moneda_pais}")

        # Determinar caja virtual o cuenta bancaria según método de pago y moneda
        # La caja física indica dónde se realizó la operación, pero el control financiero
        # se hace con cajas virtuales o cuentas bancarias
        caja_virtual = None
        cuenta_bancaria = None
        datafono = None
        banco_destino = None

        # PRIMERO: Usar la caja virtual seleccionada por el usuario si existe
        if hasattr(pago, "id_caja_virtual") and pago.id_caja_virtual:
            # Verificar si pago.id_caja_virtual ya es una instancia de Caja válida
            if (
                isinstance(pago.id_caja_virtual, Caja)
                and pago.id_caja_virtual.activa
                and pago.id_caja_virtual.empresa == empresa
            ):
                caja_virtual = pago.id_caja_virtual
                logger.debug(f"✅ Usando caja virtual seleccionada por usuario: {caja_virtual.nombre}")
            else:
                # Si no es instancia válida, intentar buscar por ID
                try:
                    caja_virtual = Caja.objects.get(id_caja=pago.id_caja_virtual_id, empresa=empresa, activa=True)
                    logger.debug(f"✅ Usando caja virtual seleccionada por usuario (por ID): {caja_virtual.nombre}")
                except (Caja.DoesNotExist, ValueError, AttributeError):
                    logger.debug(
                        f"⚠️ Caja virtual seleccionada {getattr(pago, 'id_caja_virtual_id', 'N/A')} no encontrada o inactiva, buscando automáticamente"
                    )

        # SEGUNDO: Usar la cuenta bancaria seleccionada por el usuario si existe
        if hasattr(pago, "id_cuenta_bancaria") and pago.id_cuenta_bancaria:
            # Verificar si pago.id_cuenta_bancaria ya es una instancia válida
            if (
                isinstance(pago.id_cuenta_bancaria, CuentaBancariaEmpresa)
                and pago.id_cuenta_bancaria.activo
                and pago.id_cuenta_bancaria.id_empresa == empresa
            ):
                cuenta_bancaria = pago.id_cuenta_bancaria
                logger.debug(f"✅ Usando cuenta bancaria seleccionada por usuario: {cuenta_bancaria.nombre_banco}")
            else:
                # Si no es instancia válida, intentar buscar por ID
                try:
                    cuenta_bancaria = CuentaBancariaEmpresa.objects.get(
                        id_cuenta_bancaria=pago.id_cuenta_bancaria_id, id_empresa=empresa, activo=True
                    )
                    logger.debug(
                        f"✅ Usando cuenta bancaria seleccionada por usuario (por ID): {cuenta_bancaria.nombre_banco}"
                    )
                except (CuentaBancariaEmpresa.DoesNotExist, ValueError, AttributeError):
                    logger.debug(
                        f"⚠️ Cuenta bancaria seleccionada {getattr(pago, 'id_cuenta_bancaria_id', 'N/A')} no encontrada o inactiva, buscando automáticamente"
                    )

        # Obtener método de pago y moneda (siempre necesario)
        metodo_pago = None

        # Verificar si el metodo es un UUID válido
        import uuid

        try:
            metodo_uuid = uuid.UUID(pago.metodo)
            # Es un UUID, buscar por ID
            metodo_pago = MetodoPago.objects.filter(id_metodo_pago=metodo_uuid).first()
            logger.debug(f"Método de pago encontrado por ID: {metodo_pago}")
        except ValueError:
            # No es UUID, buscar por tipo_metodo o nombre_metodo
            metodo_pago = (
                MetodoPago.objects.filter(models.Q(tipo_metodo=pago.metodo) | models.Q(nombre_metodo=pago.metodo))
                .filter(models.Q(empresa=empresa) | models.Q(es_generico=True))
                .first()
            )
            logger.debug(f"Método de pago encontrado por nombre/tipo: {metodo_pago}")

        if not metodo_pago:
            logger.debug(f"Método de pago NO encontrado: {pago.metodo}")
            return

        # Si no hay caja virtual seleccionada, buscar automáticamente según método de pago
        if not caja_virtual:
            # Determinar si usar datafono, cuenta bancaria o caja virtual según el tipo de método
            usar_datafono = metodo_pago.tipo_metodo in ["TARJETA"]
            usar_cuenta_bancaria = metodo_pago.tipo_metodo in ["CHEQUE", "CREDITO", "ELECTRONICO"]

            if usar_datafono:
                # Para pagos con tarjeta, buscar datafono disponible
                from apps.finanzas.models import Datafono

                datafono = None

                # PRIMERO: Usar el datafono seleccionado por el usuario si existe
                if hasattr(pago, "id_datafono") and pago.id_datafono:
                    if (
                        isinstance(pago.id_datafono, Datafono)
                        and pago.id_datafono.activo
                        and pago.id_datafono.id_empresa == empresa
                    ):
                        datafono = pago.id_datafono
                        logger.debug(f"✅ Usando datafono seleccionado por usuario: {datafono.nombre}")
                    else:
                        # Si no es instancia válida, intentar buscar por ID
                        try:
                            datafono = Datafono.objects.get(
                                id_datafono=pago.id_datafono, id_empresa=empresa, activo=True
                            )
                            logger.debug(f"✅ Usando datafono seleccionado por usuario (por ID): {datafono.nombre}")
                        except (Datafono.DoesNotExist, ValueError):
                            logger.debug(
                                f"⚠️ Datafono seleccionado {pago.id_datafono} no encontrado o inactivo, buscando automáticamente"
                            )

                # Si no hay datafono seleccionado, buscar automáticamente
                if not datafono:
                    # Buscar datafono que acepte este método de pago
                    datafono = Datafono.objects.filter(
                        id_empresa=empresa, activo=True
                    ).first()  # Por ahora tomar el primero disponible

                    if datafono:
                        logger.debug(f"✅ Usando datafono automático: {datafono.nombre}")
                    else:
                        logger.debug(f"⚠️ No se encontró datafono disponible para método {metodo_pago}")

                # Para pagos con tarjeta, también determinar el banco destino
                banco_destino = None
                if hasattr(pago, "banco_destino") and pago.banco_destino:
                    if (
                        isinstance(pago.banco_destino, CuentaBancariaEmpresa)
                        and pago.banco_destino.activo
                        and pago.banco_destino.id_empresa == empresa
                    ):
                        banco_destino = pago.banco_destino
                        logger.debug(f"✅ Usando banco destino seleccionado: {banco_destino.nombre_banco}")
                    else:
                        try:
                            banco_destino = CuentaBancariaEmpresa.objects.get(
                                id_cuenta_bancaria=pago.banco_destino, id_empresa=empresa, activo=True
                            )
                            logger.debug(
                                f"✅ Usando banco destino seleccionado (por ID): {banco_destino.nombre_banco}"
                            )
                        except (CuentaBancariaEmpresa.DoesNotExist, ValueError):
                            logger.debug(f"⚠️ Banco destino seleccionado {pago.banco_destino} no encontrado")

                # Si no hay banco destino seleccionado y tenemos datafono, usar la cuenta asociada al datafono
                if not banco_destino and datafono and datafono.id_cuenta_bancaria_asociada:
                    banco_destino = datafono.id_cuenta_bancaria_asociada
                    logger.debug(f"✅ Usando cuenta bancaria asociada al datafono: {banco_destino.nombre_banco}")

            elif usar_cuenta_bancaria:
                # Buscar cuenta bancaria que acepte este método de pago y moneda
                cuenta_bancaria = CuentaBancariaEmpresa.objects.filter(
                    id_empresa=empresa, activo=True, metodos_pago=metodo_pago, monedas=moneda_pago
                ).first()

                # Si no hay cuenta específica para método y moneda, buscar cuenta que acepte el método
                if not cuenta_bancaria:
                    cuenta_bancaria = CuentaBancariaEmpresa.objects.filter(
                        id_empresa=empresa, activo=True, metodos_pago=metodo_pago
                    ).first()
                    logger.debug(f"Cuenta bancaria encontrada por método {metodo_pago}: {cuenta_bancaria}")

                # Si no hay cuenta para el método, buscar cuenta que acepte la moneda
                if not cuenta_bancaria:
                    cuenta_bancaria = CuentaBancariaEmpresa.objects.filter(
                        id_empresa=empresa, activo=True, monedas=moneda_pago
                    ).first()
                    logger.debug(f"Cuenta bancaria encontrada por moneda {moneda_pago}: {cuenta_bancaria}")

                if cuenta_bancaria:
                    logger.debug(
                        f"✅ Usando cuenta bancaria automática: {cuenta_bancaria.nombre_banco} - {cuenta_bancaria.numero_cuenta}"
                    )
                else:
                    logger.debug(f"⚠️ No se encontró cuenta bancaria para método {metodo_pago} y moneda {moneda_pago}")
            else:
                # Usar caja virtual para métodos de pago en efectivo u otros
                # Buscar caja virtual que acepte este método de pago y moneda
                caja_virtual = Caja.objects.filter(
                    empresa=empresa, activa=True, metodos_pago=metodo_pago, monedas=moneda_pago
                ).first()

                # Si no hay caja específica para método y moneda, buscar caja que acepte la moneda del pago
                if not caja_virtual:
                    caja_virtual = Caja.objects.filter(empresa=empresa, activa=True, monedas=moneda_pago).first()
                    logger.debug(f"Caja virtual encontrada por moneda {moneda_pago}: {caja_virtual}")

                # Si no hay caja para la moneda, buscar caja que acepte el método
                if not caja_virtual:
                    caja_virtual = Caja.objects.filter(empresa=empresa, activa=True, metodos_pago=metodo_pago).first()
                    logger.debug(f"Caja virtual encontrada por método {metodo_pago}: {caja_virtual}")

                if caja_virtual:
                    logger.debug(f"✅ Usando caja virtual automática: {caja_virtual.nombre}")
                else:
                    logger.debug(f"⚠️ No se encontró caja virtual para método {metodo_pago} y moneda {moneda_pago}")

                # Si no hay cuenta para el método, buscar cualquier cuenta activa de la empresa
                if not cuenta_bancaria:
                    cuenta_bancaria = CuentaBancariaEmpresa.objects.filter(id_empresa=empresa, activo=True).first()

        logger.debug(
            f"Caja/Cuenta/Datafono encontrados: Caja={caja_virtual}, Cuenta={cuenta_bancaria}, Datafono={datafono}"
        )

        logger.debug(
            f"Caja/Cuenta/Datafono encontrados: Caja={caja_virtual}, Cuenta={cuenta_bancaria}, Datafono={datafono}"
        )
        logger.debug("Todas las validaciones pasaron, procediendo a crear transacción financiera")

        # Crear transacción financiera
        transaccion = TransaccionFinanciera.objects.create(
            id_empresa=empresa,
            fecha_hora_transaccion=timezone.now(),
            tipo_transaccion="INGRESO",
            monto_transaccion=pago.monto,
            id_moneda_transaccion=moneda_pago,
            id_moneda_base=moneda_base,
            id_moneda_pais_empresa=moneda_pais,
            monto_moneda_pais=monto_moneda_pais,
            monto_base_empresa=monto_base_empresa,
            id_metodo_pago=metodo_pago,
            referencia_pago=pago.referencia,
            descripcion=f"Pago de pedido {pedido.numero_pedido}",
            tipo_documento_asociado="VENTA",
            nro_documento_asociado=str(pedido.numero_pedido),
            id_caja=caja_virtual,  # Caja virtual para control financiero
            id_cuenta_bancaria=cuenta_bancaria,
            id_usuario_registro=usuario,
        )
        logger.debug(f"✅ Transacción financiera creada exitosamente: {transaccion.id_transaccion}")

        # Si se usó un datafono, crear TransaccionDatafono
        if datafono:
            from apps.finanzas.models import TransaccionDatafono

            transaccion_datafono = TransaccionDatafono.objects.create(
                id_datafono=datafono,
                monto=pago.monto,
                referencia_bancaria=pago.referencia,
                id_transaccion_financiera_origen=transaccion,
                id_usuario_registro=usuario,
            )
            logger.debug(f"✅ Transacción datafono creada: {transaccion_datafono.id_transaccion_datafono}")

        # Crear movimiento de caja/banco solo si hay caja virtual o cuenta bancaria
        if caja_virtual or cuenta_bancaria:
            saldo_anterior = (
                caja_virtual.saldo_actual if caja_virtual else (cuenta_bancaria.saldo_actual if cuenta_bancaria else 0)
            )

            # Determinar la moneda y monto para el movimiento
            # El movimiento debe estar en la moneda de la caja/cuenta, no en la moneda del pago
            if caja_virtual:
                moneda_movimiento = caja_virtual.moneda
                # Si la moneda del pago es diferente a la moneda de la caja, convertir
                if moneda_pago != moneda_movimiento:
                    if moneda_pago == moneda_base and moneda_movimiento == moneda_pais:
                        # Convertir de base a país: multiplicar por tasa
                        monto_movimiento = pago.monto * (pago.tasa if pago.tasa > 0 else 1)
                    elif moneda_pago == moneda_pais and moneda_movimiento == moneda_base:
                        # Convertir de país a base: dividir por tasa
                        monto_movimiento = pago.monto / (pago.tasa if pago.tasa > 0 else 1)
                    else:
                        # Para otras conversiones, usar la tasa proporcionada
                        monto_movimiento = pago.monto * (pago.tasa if pago.tasa > 0 else 1)
                else:
                    # Misma moneda, usar monto directo
                    monto_movimiento = pago.monto
            else:
                # Para cuentas bancarias, usar la moneda de la cuenta
                moneda_movimiento = cuenta_bancaria.id_moneda
                # Si la moneda del pago es diferente a la moneda de la cuenta, convertir
                if moneda_pago != moneda_movimiento:
                    if moneda_pago == moneda_base and moneda_movimiento == moneda_pais:
                        monto_movimiento = pago.monto * (pago.tasa if pago.tasa > 0 else 1)
                    elif moneda_pago == moneda_pais and moneda_movimiento == moneda_base:
                        monto_movimiento = pago.monto / (pago.tasa if pago.tasa > 0 else 1)
                    else:
                        monto_movimiento = pago.monto * (pago.tasa if pago.tasa > 0 else 1)
                else:
                    monto_movimiento = pago.monto

            # Convertir monto_movimiento a Decimal para evitar errores de tipo
            from decimal import Decimal

            monto_movimiento = Decimal(str(monto_movimiento))

            movimiento = MovimientoCajaBanco.objects.create(
                id_empresa=empresa,
                fecha_movimiento=timezone.now().date(),
                hora_movimiento=timezone.now().time(),
                tipo_movimiento="INGRESO",
                monto=monto_movimiento,
                id_moneda=moneda_movimiento,
                concepto=f"Pago de pedido {pedido.numero_pedido}",
                referencia=pago.referencia,
                id_caja=caja_virtual,  # Caja virtual para el movimiento
                id_cuenta_bancaria=cuenta_bancaria,
                id_transaccion_financiera=transaccion,
                saldo_anterior=saldo_anterior,
                saldo_nuevo=saldo_anterior + monto_movimiento,
                id_usuario_registro=usuario,
            )

            # Actualizar saldo de caja virtual, física o cuenta bancaria
            if caja_virtual:
                caja_virtual.saldo_actual = movimiento.saldo_nuevo
                caja_virtual.save()
            elif cuenta_bancaria:
                cuenta_bancaria.saldo_actual = movimiento.saldo_nuevo
                cuenta_bancaria.save()

            logger.debug(f"✅ Movimiento de caja/banco creado: {movimiento.id_movimiento}")

    except Exception as e:
        logger.exception("Error crítico creando transacción financiera: %s", e)
        raise


class PedidoViewSet(viewsets.ModelViewSet):
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar pedidos por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return Pedido.objects.filter(id_empresa__in=empresas_visibles).order_by("-fecha_pedido", "-fecha_creacion")

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # Asegurarse de que el número de pedido esté en la respuesta
        if hasattr(response, "data") and "numero_pedido" not in response.data:
            # Buscar el objeto creado y agregar el número
            instance = self.get_object() if hasattr(self, "get_object") else None
            if instance and hasattr(instance, "numero_pedido"):
                response.data["numero_pedido"] = instance.numero_pedido
        return response

    @action(detail=True, methods=["post"], url_path="confirmar")
    def confirmar(self, request, pk=None):
        """
        POST /api/ventas/pedidos/{pk}/confirmar/
        Body: {"almacen_id": "uuid", "generar_cxc": true|false (opcional)}

        Cambia estado a APROBADO, descuenta stock e (opcionalmente) genera CxC.
        """
        from apps.almacenes.models import Almacen
        from .services import PedidoConfirmacionError, confirmar_pedido

        pedido = self.get_object()
        almacen_id = request.data.get("almacen_id")
        if not almacen_id:
            raise ValidationError({"almacen_id": "Este campo es requerido."})

        try:
            almacen = Almacen.objects.get(pk=almacen_id, id_empresa=pedido.id_empresa)
        except Almacen.DoesNotExist:
            raise ValidationError({"almacen_id": "Almacén no encontrado en esta empresa."})

        generar_cxc = request.data.get("generar_cxc")
        if generar_cxc is not None:
            generar_cxc = bool(generar_cxc)

        try:
            resultado = confirmar_pedido(
                pedido=pedido,
                almacen=almacen,
                usuario=request.user,
                generar_cxc=generar_cxc,
            )
        except PedidoConfirmacionError as exc:
            raise ValidationError(str(exc)) from exc

        return Response(
            {
                "pedido_id": str(pedido.id_pedido),
                "numero_pedido": pedido.numero_pedido,
                "estado": pedido.estado,
                "reservas_creadas": len(resultado["reservas"]),
                "cxc_generada": resultado["cxc"] is not None,
                "cxc_id": str(resultado["cxc"].pk) if resultado["cxc"] else None,
            },
            status=status.HTTP_200_OK,
        )


class DetallePedidoViewSet(viewsets.ModelViewSet):
    queryset = DetallePedido.objects.all()
    serializer_class = DetallePedidoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetallePedido.objects.filter(id_pedido__id_empresa__in=_empresas(self.request))


class NotaVentaViewSet(viewsets.ModelViewSet):
    queryset = NotaVenta.objects.all()
    serializer_class = NotaVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1
        return NotaVenta.objects.filter(id_empresa__in=_empresas(self.request)).order_by("-fecha_creacion")


class DetalleNotaVentaViewSet(viewsets.ModelViewSet):
    queryset = DetalleNotaVenta.objects.all()
    serializer_class = DetalleNotaVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleNotaVenta.objects.filter(id_nota_venta__id_empresa__in=_empresas(self.request))


class FacturaFiscalViewSet(viewsets.ModelViewSet):
    queryset = FacturaFiscal.objects.all()
    serializer_class = FacturaFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar facturas por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return FacturaFiscal.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_emision", "-fecha_creacion"
        )

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/ventas/facturas-fiscales/{id}/pdf/ — devuelve el PDF de la factura."""
        from django.http import HttpResponse
        from apps.fiscal.pdf_factura import generar_pdf_factura

        factura = self.get_object()
        try:
            pdf_bytes = generar_pdf_factura(factura)
        except ImportError as exc:
            return Response({"error": str(exc)}, status=503)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="factura_{factura.numero_factura}.pdf"'
        )
        return response


class DetalleFacturaFiscalViewSet(viewsets.ModelViewSet):
    queryset = DetalleFacturaFiscal.objects.all()
    serializer_class = DetalleFacturaFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleFacturaFiscal.objects.filter(id_factura__id_empresa__in=_empresas(self.request))


class NotaCreditoVentaViewSet(viewsets.ModelViewSet):
    queryset = NotaCreditoVenta.objects.all()
    serializer_class = NotaCreditoVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar notas de crédito por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return NotaCreditoVenta.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_emision", "-fecha_creacion"
        )


class DetalleNotaCreditoVentaViewSet(viewsets.ModelViewSet):
    queryset = DetalleNotaCreditoVenta.objects.all()
    serializer_class = DetalleNotaCreditoVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleNotaCreditoVenta.objects.filter(id_nota_credito__id_empresa__in=_empresas(self.request))


class DevolucionVentaViewSet(viewsets.ModelViewSet):
    queryset = DevolucionVenta.objects.all()
    serializer_class = DevolucionVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar devoluciones por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return DevolucionVenta.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_devolucion", "-fecha_creacion"
        )


class DetalleDevolucionVentaViewSet(viewsets.ModelViewSet):
    queryset = DetalleDevolucionVenta.objects.all()
    serializer_class = DetalleDevolucionVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleDevolucionVenta.objects.filter(id_devolucion__id_empresa__in=_empresas(self.request))


class CotizacionViewSet(viewsets.ModelViewSet):
    queryset = Cotizacion.objects.all()
    serializer_class = CotizacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar cotizaciones por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return Cotizacion.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_cotizacion", "-fecha_creacion"
        )

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/ventas/cotizaciones/{id}/pdf/ — devuelve el PDF de la cotización."""
        from django.http import HttpResponse
        from apps.ventas.pdf_cotizacion import generar_pdf_cotizacion

        cotizacion = self.get_object()
        try:
            pdf_bytes = generar_pdf_cotizacion(cotizacion)
        except ImportError as exc:
            return Response({"error": str(exc)}, status=503)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="cotizacion_{cotizacion.numero_cotizacion}.pdf"'
        )
        return response


class DetalleCotizacionViewSet(viewsets.ModelViewSet):
    queryset = DetalleCotizacion.objects.all()
    serializer_class = DetalleCotizacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleCotizacion.objects.filter(id_cotizacion__id_empresa__in=_empresas(self.request))


class NotaCreditoFiscalViewSet(viewsets.ModelViewSet):
    queryset = NotaCreditoFiscal.objects.all()
    serializer_class = NotaCreditoFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrar notas de crédito fiscal por empresas visibles del usuario"""
        from apps.core.viewsets import get_empresas_visible

        user = self.request.user
        empresas_visibles = get_empresas_visible(user)
        return NotaCreditoFiscal.objects.filter(id_empresa__in=empresas_visibles).order_by(
            "-fecha_emision", "-fecha_creacion"
        )


class DetalleNotaCreditoFiscalViewSet(viewsets.ModelViewSet):
    queryset = DetalleNotaCreditoFiscal.objects.all()
    serializer_class = DetalleNotaCreditoFiscalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1 via parent
        return DetalleNotaCreditoFiscal.objects.filter(
            id_nota_credito_fiscal__id_empresa__in=_empresas(self.request)
        )


class ListaPrecioViewSet(viewsets.ModelViewSet):
    queryset = ListaPrecio.objects.all()
    serializer_class = ListaPrecioSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["activo", "es_referencia", "id_empresa"]
    search_fields = ["nombre", "codigo"]
    ordering_fields = ["nombre", "codigo", "fecha_creacion"]
    ordering = ["codigo"]

    def get_queryset(self):
        # R-CODE-1
        return ListaPrecio.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=True, methods=["post"], url_path="importar-masivo")
    def importar_masivo(self, request, pk=None):
        """
        Importa precios masivamente desde un CSV.

        Formato esperado del CSV:
            codigo_producto,precio,precio_minimo,vigente_desde,vigente_hasta
            PROD-001,15.50,12.00,2026-01-01,2026-12-31
        """
        import csv
        import io

        lista = self.get_object()
        archivo = request.FILES.get("archivo")

        if not archivo:
            return Response(
                {"error": "Debe adjuntar un archivo CSV en el campo 'archivo'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.inventario.models import Producto

        content = archivo.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))

        creados = 0
        actualizados = 0
        errores = []

        for idx, row in enumerate(reader, start=2):  # start=2 porque fila 1 es cabecera
            codigo = (row.get("codigo_producto") or "").strip()
            if not codigo:
                errores.append({"fila": idx, "error": "codigo_producto vacío"})
                continue

            try:
                producto = Producto.objects.get(codigo_producto=codigo, id_empresa=lista.id_empresa)
            except Producto.DoesNotExist:
                errores.append({"fila": idx, "error": f"Producto '{codigo}' no encontrado en esta empresa"})
                continue
            except Exception as exc:
                errores.append({"fila": idx, "error": str(exc)})
                continue

            try:
                precio = Decimal(str(row.get("precio", 0) or 0))
                precio_minimo = Decimal(str(row.get("precio_minimo", 0) or 0))
                vigente_desde = row.get("vigente_desde") or None
                vigente_hasta = row.get("vigente_hasta") or None

                detalle, created = DetallePrecio.objects.update_or_create(
                    id_lista=lista,
                    id_producto=producto,
                    defaults={
                        "precio": precio,
                        "precio_minimo": precio_minimo,
                        "vigente_desde": vigente_desde,
                        "vigente_hasta": vigente_hasta,
                        "activo": True,
                    },
                )
                if created:
                    creados += 1
                else:
                    actualizados += 1
            except Exception as exc:
                errores.append({"fila": idx, "error": str(exc)})

        return Response(
            {
                "lista": str(lista),
                "creados": creados,
                "actualizados": actualizados,
                "errores": errores,
                "total_errores": len(errores),
            },
            status=status.HTTP_200_OK if not errores else status.HTTP_207_MULTI_STATUS,
        )


class DetallePrecioViewSet(viewsets.ModelViewSet):
    queryset = DetallePrecio.objects.all()
    serializer_class = DetallePrecioSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["activo", "id_lista", "id_producto"]
    ordering_fields = ["id_lista", "id_producto"]
    ordering = ["id_lista"]

    def get_queryset(self):
        # R-CODE-1 via ListaPrecio → id_empresa
        return DetallePrecio.objects.filter(id_lista__id_empresa__in=_empresas(self.request))
