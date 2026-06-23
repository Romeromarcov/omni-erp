from apps.core.uuid import uuid7

from django.db import models


class CategoriaGasto(models.Model):
    id_categoria_gasto = models.UUIDField(primary_key=True, default=uuid7)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    nombre_categoria = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    # Cuenta contable de gasto (DEUDORA) a la que se imputa por defecto el gasto
    # de esta categoría. SET_NULL: la categoría sobrevive al borrado de la cuenta.
    id_cuenta_contable = models.ForeignKey(
        "contabilidad.PlanCuentas",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="categorias_gasto",
    )
    # Si True, el gasto debe tener factura de respaldo (tiene_factura=True) para
    # poder aprobarse. Mapea ExpenseCategory.requires_invoice del plan.
    requiere_factura = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre_categoria} ({self.id_empresa_id})"


class Gasto(models.Model):
    id_gasto = models.UUIDField(primary_key=True, default=uuid7)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    fecha_gasto = models.DateField()
    descripcion = models.TextField()
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    # Porción de IVA crédito fiscal incluida en `monto` (0 si no aplica). El
    # asiento separa base (GASTO) e IVA (GASTO_IVA), espejo de ventas (CTF-001).
    monto_iva = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE)
    # Multi-moneda: tasa a moneda base al registrar el gasto (referencia).
    tasa_cambio = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    id_categoria_gasto = models.ForeignKey("CategoriaGasto", on_delete=models.CASCADE)
    # Proveedor/contacto del gasto (opcional: gasto interno puede no tenerlo).
    id_proveedor = models.ForeignKey(
        "proveedores.Proveedor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos",
    )
    # Producto de gasto opcional (gasto con producto vs. cuenta manual).
    id_producto = models.ForeignKey(
        "inventario.Producto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos",
    )
    # Respaldo documental: tiene_factura mapea has_invoice. numero_factura guarda
    # la referencia. sin_respaldo se marca al aprobar un gasto sin factura.
    tiene_factura = models.BooleanField(default=False)
    numero_factura = models.CharField(max_length=100, null=True, blank=True)
    sin_respaldo = models.BooleanField(default=False)
    # FK real al empleado responsable (deuda: antes solo el UUIDField temporal,
    # que ningún flujo poblaba). SET_NULL: el gasto sobrevive al borrado.
    id_empleado_responsable = models.ForeignKey(
        "rrhh.Empleado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_responsable",
    )
    id_empleado_responsable_temp = models.UUIDField(null=True, blank=True)  # Deprecado por id_empleado_responsable
    estado_gasto = models.CharField(
        max_length=20,
        choices=[
            ("PENDIENTE_APROBACION", "Pendiente Aprobación"),
            ("APROBADO", "Aprobado"),
            ("RECHAZADO", "Rechazado"),
            ("REEMBOLSADO", "Reembolsado"),
            ("CONTABILIZADO", "Contabilizado"),
        ],
        default="PENDIENTE_APROBACION",
    )
    # FK real al usuario que registró (deuda: antes solo el UUIDField temporal).
    id_usuario_registro = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gastos_registrados",
    )
    id_usuario_registro_temp = models.UUIDField(null=True, blank=True)  # Deprecado por id_usuario_registro
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Gasto {self.descripcion[:30]} ({self.monto})"


class DetalleGasto(models.Model):
    """Línea de imputación de un gasto a una cuenta contable (ExpenseLine).

    Permite desglosar un gasto en varias cuentas. Si un gasto no tiene detalles,
    se imputa a la cuenta de su categoría.
    """

    id_detalle_gasto = models.UUIDField(primary_key=True, default=uuid7)
    id_gasto = models.ForeignKey("Gasto", on_delete=models.CASCADE, related_name="detalles")
    id_cuenta_contable = models.ForeignKey(
        "contabilidad.PlanCuentas",
        on_delete=models.PROTECT,
        related_name="detalles_gasto",
    )
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    monto_iva = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    def __str__(self):
        return f"Detalle {self.id_cuenta_contable_id}: {self.monto}"


class ReembolsoGasto(models.Model):
    id_reembolso = models.UUIDField(primary_key=True, default=uuid7)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    id_gasto = models.ForeignKey("Gasto", on_delete=models.CASCADE)
    # FK real al empleado a reembolsar (deuda: antes solo el UUIDField temporal).
    id_empleado = models.ForeignKey(
        "rrhh.Empleado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reembolsos",
    )
    id_empleado_temp = models.UUIDField(null=True, blank=True)  # Deprecado por id_empleado
    monto_reembolso = models.DecimalField(max_digits=18, decimal_places=2)
    id_moneda = models.ForeignKey("finanzas.Moneda", on_delete=models.CASCADE)
    id_metodo_pago = models.ForeignKey("finanzas.MetodoPago", on_delete=models.CASCADE)
    fecha_reembolso = models.DateField()
    estado_reembolso = models.CharField(
        max_length=20, choices=[("PENDIENTE", "Pendiente"), ("PAGADO", "Pagado"), ("ANULADO", "Anulado")]
    )
    # FK real al usuario que registró (deuda: antes solo el UUIDField temporal).
    id_usuario_registro = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reembolsos_registrados",
    )
    id_usuario_registro_temp = models.UUIDField(null=True, blank=True)  # Deprecado por id_usuario_registro
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reembolso {self.monto_reembolso} ({self.estado_reembolso})"
