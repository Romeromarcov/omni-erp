"""
TRACK-1F-1 · Importación de clientes desde CSV.

Uso:
    python manage.py importar_clientes --archivo clientes.csv --empresa <uuid|identificador>
    python manage.py importar_clientes --archivo clientes.csv --empresa <...> --confirm

Columnas CSV esperadas (cabecera):
    razon_social (req), rif (req), nombre_comercial, direccion, telefono,
    email, tipo_cliente (CONTADO|CREDITO), limite_credito, dias_credito

Idempotente: si ya existe un Cliente con ese ``rif`` en la empresa, se
ACTUALIZA en lugar de duplicar.
"""

from apps.crm.models import Cliente

from ._importador_base import FilaError, ImportadorBaseCommand


class Command(ImportadorBaseCommand):
    help = "Importa/actualiza clientes (crm.Cliente) desde un CSV, idempotente por RIF."
    nombre_entidad = "cliente"

    TIPOS_VALIDOS = {"CONTADO", "CREDITO"}

    def procesar_fila(self, empresa, fila, numero_linea):
        razon_social = self.requerido(fila, "razon_social")
        rif = self.requerido(fila, "rif")

        tipo_cliente = self.opcional(fila, "tipo_cliente", "CONTADO").upper()
        if tipo_cliente not in self.TIPOS_VALIDOS:
            raise FilaError(
                f"tipo_cliente inválido '{tipo_cliente}'; use CONTADO o CREDITO."
            )

        datos = {
            "razon_social": razon_social,
            "nombre_comercial": self.opcional(fila, "nombre_comercial") or None,
            "direccion": self.opcional(fila, "direccion") or None,
            "telefono": self.opcional(fila, "telefono") or None,
            "email": self.opcional(fila, "email") or None,
            "tipo_cliente": tipo_cliente,
            "limite_credito": self.a_decimal(fila.get("limite_credito"), "limite_credito"),
            "dias_credito": int(self.opcional(fila, "dias_credito", "0") or "0"),
        }

        cliente = Cliente.objects.filter(id_empresa=empresa, rif=rif).first()
        if cliente is not None:
            for campo, valor in datos.items():
                setattr(cliente, campo, valor)
            cliente.full_clean(exclude=["contacto"])
            cliente.save()
            return "actualizado"

        cliente = Cliente(id_empresa=empresa, rif=rif, **datos)
        cliente.full_clean(exclude=["contacto"])
        cliente.save()
        return "creado"
