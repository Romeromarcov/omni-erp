"""
TRACK-1F-4 · Importación de saldos de cuentas por cobrar desde CSV.

Uso:
    python manage.py importar_saldos_cxc --archivo saldos.csv --empresa <uuid|identificador>
    python manage.py importar_saldos_cxc --archivo saldos.csv --empresa <...> --confirm

Columnas CSV esperadas (cabecera):
    rif (req, vincula al Cliente), monto (req), fecha_emision (req, YYYY-MM-DD),
    fecha_vencimiento (req, YYYY-MM-DD), referencia_externa, estado, descripcion

Vincula al ``crm.Cliente`` por RIF dentro de la empresa y crea la cabecera de
``cuentas_por_cobrar.CuentaPorCobrar`` con el saldo inicial.

Idempotente cuando se provee ``referencia_externa``: si ya existe una CxC con
esa referencia para el mismo cliente/empresa, se ACTUALIZA. Sin
``referencia_externa`` siempre se crea un registro nuevo.
"""

from datetime import datetime

from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import CuentaPorCobrar

from ._importador_base import FilaError, ImportadorBaseCommand


class Command(ImportadorBaseCommand):
    help = (
        "Importa saldos iniciales de CxC (cuentas_por_cobrar.CuentaPorCobrar) desde un CSV, "
        "vinculando al Cliente por RIF."
    )
    nombre_entidad = "saldo CxC"

    ESTADOS_VALIDOS = {"pendiente", "pagada", "vencida", "parcial"}

    @staticmethod
    def _fecha(fila, clave):
        valor = (fila.get(clave) or "").strip()
        if not valor:
            raise FilaError(f"falta el campo de fecha requerido '{clave}'.")
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            raise FilaError(
                f"el campo '{clave}' no es una fecha válida (use YYYY-MM-DD): '{valor}'."
            )

    def procesar_fila(self, empresa, fila, numero_linea):
        rif = self.requerido(fila, "rif")

        cliente = Cliente.objects.filter(id_empresa=empresa, rif=rif).first()
        if cliente is None:
            raise FilaError(
                f"no existe un cliente con rif '{rif}' en la empresa."
            )

        monto = self.a_decimal(self.requerido(fila, "monto"), "monto")
        fecha_emision = self._fecha(fila, "fecha_emision")
        fecha_vencimiento = self._fecha(fila, "fecha_vencimiento")

        estado = self.opcional(fila, "estado", "pendiente").lower()
        if estado not in self.ESTADOS_VALIDOS:
            raise FilaError(
                f"estado inválido '{estado}'; use uno de {sorted(self.ESTADOS_VALIDOS)}."
            )

        referencia_externa = self.opcional(fila, "referencia_externa") or None
        descripcion = self.opcional(fila, "descripcion") or None

        datos = {
            "monto": monto,
            "fecha_emision": fecha_emision,
            "fecha_vencimiento": fecha_vencimiento,
            "estado": estado,
            "descripcion": descripcion,
        }

        if referencia_externa:
            cxc = CuentaPorCobrar.objects.filter(
                empresa=empresa,
                cliente=cliente,
                referencia_externa=referencia_externa,
            ).first()
            if cxc is not None:
                for campo, valor in datos.items():
                    setattr(cxc, campo, valor)
                cxc.save()
                return "actualizado"

        CuentaPorCobrar.objects.create(
            empresa=empresa,
            cliente=cliente,
            referencia_externa=referencia_externa,
            **datos,
        )
        return "creado"
