"""
TRACK-1F-3 · Importación de inventario inicial (StockActual) desde CSV.

Uso:
    python manage.py importar_inventario_inicial --archivo stock.csv --empresa <uuid|identificador>
    python manage.py importar_inventario_inicial --archivo stock.csv --empresa <...> --confirm

Columnas CSV esperadas (cabecera):
    sku (req), almacen (req, codigo_almacen), cantidad_disponible (req),
    cantidad_minima, cantidad_maxima

Resuelve el producto por ``sku`` y el almacén por ``codigo_almacen`` dentro de
la empresa. Idempotente: si ya existe StockActual para (producto, almacén)
[sin variante], se ACTUALIZAN las cantidades en lugar de duplicar.
"""

from apps.almacenes.models import Almacen
from apps.inventario.models import Producto, StockActual

from ._importador_base import FilaError, ImportadorBaseCommand


class Command(ImportadorBaseCommand):
    help = (
        "Importa el stock inicial (inventario.StockActual) por almacén desde un CSV, "
        "idempotente por (producto, almacén)."
    )
    nombre_entidad = "registro de stock"

    def procesar_fila(self, empresa, fila, numero_linea):
        sku = self.requerido(fila, "sku")
        codigo_almacen = self.requerido(fila, "almacen")

        producto = Producto.objects.filter(id_empresa=empresa, sku=sku).first()
        if producto is None:
            raise FilaError(
                f"no existe un producto con sku '{sku}' en la empresa."
            )

        almacen = Almacen.objects.filter(
            id_empresa=empresa, codigo_almacen=codigo_almacen
        ).first()
        if almacen is None:
            raise FilaError(
                f"no existe un almacén con codigo_almacen '{codigo_almacen}' en la empresa."
            )

        cantidad_disponible = self.a_decimal(
            self.requerido(fila, "cantidad_disponible"), "cantidad_disponible"
        )
        cantidad_minima = self.a_decimal(fila.get("cantidad_minima"), "cantidad_minima")
        cantidad_maxima = self.a_decimal(fila.get("cantidad_maxima"), "cantidad_maxima")

        stock = StockActual.objects.filter(
            id_producto=producto, id_variante__isnull=True, id_almacen=almacen
        ).first()
        if stock is not None:
            stock.id_empresa = empresa
            stock.cantidad_disponible = cantidad_disponible
            stock.cantidad_minima = cantidad_minima
            stock.cantidad_maxima = cantidad_maxima
            stock.save()
            return "actualizado"

        StockActual.objects.create(
            id_empresa=empresa,
            id_producto=producto,
            id_almacen=almacen,
            cantidad_disponible=cantidad_disponible,
            cantidad_minima=cantidad_minima,
            cantidad_maxima=cantidad_maxima,
        )
        return "creado"
