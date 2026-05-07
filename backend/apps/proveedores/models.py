from django.db import models
import uuid

class Proveedor(models.Model):
    id_proveedor = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    razon_social = models.CharField(max_length=255)
    nombre_comercial = models.CharField(max_length=255, null=True, blank=True)
    rif = models.CharField(max_length=20, unique=True)
    direccion = models.TextField(null=True, blank=True)
    telefono = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    contacto = models.CharField(max_length=100, null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.razon_social


class ContactoProveedor(models.Model):
    id_contacto = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_proveedor = models.ForeignKey('Proveedor', on_delete=models.CASCADE, related_name='contactos')
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100, null=True, blank=True)
    telefono = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    es_contacto_principal = models.BooleanField(default=False)
    area_responsabilidad = models.CharField(max_length=100, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'proveedores_contacto_proveedor'
        verbose_name = 'Contacto de Proveedor'
        verbose_name_plural = 'Contactos de Proveedores'

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class CuentaBancariaProveedor(models.Model):
    id_cuenta_bancaria = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_proveedor = models.ForeignKey('Proveedor', on_delete=models.CASCADE, related_name='cuentas_bancarias')
    nombre_banco = models.CharField(max_length=100)
    numero_cuenta = models.CharField(max_length=50)
    tipo_cuenta = models.CharField(max_length=20, choices=[
        ('CORRIENTE', 'Corriente'),
        ('AHORRO', 'Ahorro'),
        ('VISTA', 'Vista'),
        ('PLAZO_FIJO', 'Plazo Fijo')
    ])
    moneda = models.ForeignKey('finanzas.Moneda', on_delete=models.CASCADE, related_name='cuentas_proveedores')
    titular_cuenta = models.CharField(max_length=200, null=True, blank=True)
    identificacion_titular = models.CharField(max_length=50, null=True, blank=True)
    es_cuenta_principal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'proveedores_cuenta_bancaria_proveedor'
        verbose_name = 'Cuenta Bancaria de Proveedor'
        verbose_name_plural = 'Cuentas Bancarias de Proveedores'
        unique_together = ['nombre_banco', 'numero_cuenta']

    def __str__(self):
        return f"{self.id_proveedor.razon_social} - {self.nombre_banco} ({self.numero_cuenta})"
