"""
Servicios de negocio compartidos del módulo Core.

verificar_paso_flujo() — comprueba si un paso del ciclo de documentos
está configurado como obligatorio para la empresa.
"""

from __future__ import annotations


class FlujoError(Exception):
    """Se lanza cuando un paso requerido del flujo de documentos no se cumple."""


def es_paso_obligatorio(empresa, tipo_documento: str, paso: str) -> bool:
    """
    Devuelve True si el paso está marcado como obligatorio para la empresa.

    Si no existe configuración para ese paso, asume obligatorio=False
    (comportamiento permisivo — no exige el paso hasta que se configure).

    Args:
        empresa:         Instancia Empresa (o UUID / id_empresa).
        tipo_documento:  'VENTAS' | 'COMPRAS'
        paso:            'COTIZACION' | 'PEDIDO' | 'NOTA_ENTREGA' | 'FACTURA' |
                         'SOLICITUD' | 'ORDEN_COMPRA' | 'RECEPCION' | 'FACTURA_COMPRA'

    Returns:
        bool
    """
    from .models import ConfiguracionFlujoDocumentos

    config = ConfiguracionFlujoDocumentos.objects.filter(
        id_empresa=empresa,
        tipo_documento=tipo_documento,
        paso=paso,
        activo=True,
    ).first()

    if config is None:
        return False  # permisivo: sin configuración explícita → no se exige el paso
    return config.obligatorio


def verificar_paso_flujo(empresa, tipo_documento: str, paso: str, cumplido: bool) -> None:
    """
    Verifica que un paso requerido haya sido cumplido.

    Si el paso es obligatorio y ``cumplido=False``, lanza FlujoError.
    Si el paso no es obligatorio, no hace nada independientemente de ``cumplido``.

    Args:
        empresa:         Instancia Empresa.
        tipo_documento:  'VENTAS' | 'COMPRAS'
        paso:            Nombre del paso previo que se está verificando.
        cumplido:        True si el paso ya fue completado.

    Raises:
        FlujoError si el paso es obligatorio y no fue cumplido.
    """
    if es_paso_obligatorio(empresa, tipo_documento, paso) and not cumplido:
        raise FlujoError(
            f"El paso '{paso}' es obligatorio en el flujo {tipo_documento} "
            f"para la empresa '{empresa}' y no ha sido completado."
        )
