from django.db import models
from django.db.models import Q

from apps.crm.models import Cliente


class CuentaPorCobrar(models.Model):
    # ADR-009 / Plan D-D1: la FK a crm.Cliente es OPCIONAL. Una cuenta por cobrar
    # puede nacer de una fuente externa (p. ej. Odoo vía Integration Hub) sin que
    # exista un crm.Cliente en Omni. En ese caso se identifica al deudor con
    # `cliente_externo_id` (mismo patrón string-flexible que GestionCobranza) y
    # se denormaliza el nombre en `cliente_nombre`. Una de las dos formas de
    # identificación es obligatoria (ver CheckConstraint).
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="cuentas_por_cobrar",
        null=True,
        blank=True,
    )
    cliente_externo_id = models.CharField(
        max_length=100, blank=True, default="",
        help_text="ID del deudor en la fuente externa (p. ej. partner_id de Odoo). "
                  "Se usa cuando no hay FK a crm.Cliente.",
    )
    cliente_externo_nombre = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Nombre del deudor denormalizado (fuente externa sin crm.Cliente).",
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, null=True, blank=True)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=[("pendiente", "Pendiente"), ("pagada", "Pagada"), ("vencida", "Vencida"), ("parcial", "Parcial")],
        default="pendiente",
    )
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            # Integridad: toda CxC identifica a su deudor por FK o por id externo.
            models.CheckConstraint(
                condition=Q(cliente__isnull=False) | ~Q(cliente_externo_id=""),
                name="cxc_cliente_o_externo_requerido",
            ),
        ]

    @property
    def cliente_ref(self) -> str:
        """
        Identificador agnóstico del deudor: el id de la FK crm.Cliente si existe,
        o el id externo (Odoo) en su defecto. Es el valor que usan los providers
        de cartera y los eventos, sin importar el origen.
        """
        if self.cliente_id:
            return str(self.cliente_id)
        return self.cliente_externo_id or ""

    @property
    def cliente_display(self) -> str:
        """Nombre legible del deudor (razón social del FK o nombre externo)."""
        if self.cliente_id and self.cliente:
            return getattr(self.cliente, "razon_social", "") or str(self.cliente)
        return self.cliente_externo_nombre or self.cliente_externo_id or "—"

    def __str__(self):
        return f"{self.cliente_display} - {self.monto} ({self.estado})"


# Modelo AbonoCxC movido aquí para evitar import circular
from apps.core.models import Usuarios


class AbonoCxC(models.Model):
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    cuenta_por_cobrar = models.ForeignKey(CuentaPorCobrar, on_delete=models.CASCADE, related_name="abonos")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_abono = models.DateField(auto_now_add=True)
    usuario = models.ForeignKey(Usuarios, on_delete=models.SET_NULL, null=True, blank=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Abono de {self.monto} a {self.cuenta_por_cobrar}"
