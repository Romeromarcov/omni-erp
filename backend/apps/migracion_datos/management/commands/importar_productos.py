"""
TRACK-1F-2 · Importación de productos desde CSV.

Uso:
    python manage.py importar_productos --archivo productos.csv --empresa <uuid|identificador>
    python manage.py importar_productos --archivo productos.csv --empresa <...> --confirm

Columnas CSV esperadas (cabecera):
    sku (req), nombre_producto (req), categoria (req, nombre de categoría),
    unidad_medida (req, abreviatura), moneda (req, código ISO),
    descripcion, tipo_producto (PRODUCTO_FISICO|SERVICIO|KIT|COMBO),
    costo_promedio, precio_venta_sugerido

Dependencias resueltas dentro de la empresa:
  - categoria  -> inventario.CategoriaProducto (get_or_create por nombre)
  - unidad     -> inventario.UnidadMedida (get_or_create por abreviatura)
  - moneda     -> finanzas.Moneda por código ISO (debe existir)

Idempotente: si ya existe un Producto con ese ``sku`` en la empresa, se
ACTUALIZA en lugar de duplicar.
"""

from apps.finanzas.models import Moneda
from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

from ._importador_base import FilaError, ImportadorBaseCommand


class Command(ImportadorBaseCommand):
    help = "Importa/actualiza productos (inventario.Producto) desde un CSV, idempotente por SKU."
    nombre_entidad = "producto"

    TIPOS_VALIDOS = {"PRODUCTO_FISICO", "SERVICIO", "KIT", "COMBO"}

    def _resolver_categoria(self, empresa, nombre):
        cat, _ = CategoriaProducto.objects.get_or_create(
            id_empresa=empresa,
            nombre_categoria=nombre,
        )
        return cat

    def _resolver_unidad(self, empresa, abreviatura):
        unidad = UnidadMedida.objects.filter(
            id_empresa=empresa, abreviatura=abreviatura
        ).first()
        if unidad is None:
            unidad = UnidadMedida.objects.create(
                id_empresa=empresa,
                nombre=abreviatura,
                abreviatura=abreviatura,
                tipo="CANTIDAD",
            )
        return unidad

    def _resolver_moneda(self, codigo_iso):
        moneda = Moneda.objects.filter(codigo_iso=codigo_iso).first()
        if moneda is None:
            raise FilaError(
                f"no existe una moneda con código ISO '{codigo_iso}'. "
                f"Créela antes de importar."
            )
        return moneda

    def procesar_fila(self, empresa, fila, numero_linea):
        sku = self.requerido(fila, "sku")
        nombre_producto = self.requerido(fila, "nombre_producto")
        categoria_nombre = self.requerido(fila, "categoria")
        unidad_abrev = self.requerido(fila, "unidad_medida")
        moneda_iso = self.requerido(fila, "moneda")

        tipo_producto = self.opcional(fila, "tipo_producto", "PRODUCTO_FISICO").upper()
        if tipo_producto not in self.TIPOS_VALIDOS:
            raise FilaError(
                f"tipo_producto inválido '{tipo_producto}'; "
                f"use uno de {sorted(self.TIPOS_VALIDOS)}."
            )

        categoria = self._resolver_categoria(empresa, categoria_nombre)
        unidad = self._resolver_unidad(empresa, unidad_abrev)
        moneda = self._resolver_moneda(moneda_iso)

        datos = {
            "nombre_producto": nombre_producto,
            "id_categoria": categoria,
            "id_unidad_medida_base": unidad,
            "id_moneda_precio": moneda,
            "descripcion": self.opcional(fila, "descripcion") or None,
            "tipo_producto": tipo_producto,
            "costo_promedio": self.a_decimal(fila.get("costo_promedio"), "costo_promedio"),
            "precio_venta_sugerido": self.a_decimal(
                fila.get("precio_venta_sugerido"), "precio_venta_sugerido"
            ),
        }

        producto = Producto.objects.filter(id_empresa=empresa, sku=sku).first()
        if producto is not None:
            for campo, valor in datos.items():
                setattr(producto, campo, valor)
            producto.save()
            return "actualizado"

        producto = Producto(id_empresa=empresa, sku=sku, **datos)
        producto.save()
        return "creado"
