from django.db import models
import uuid
from django.core.exceptions import ValidationError
import re

def validar_rif(value):
    # Validar formato RIF: Letra-Mayúscula seguida de guion y números
    if not re.match(r'^[VJEGBP]-[0-9]+$', value):
        raise ValidationError('RIF debe tener formato Letra-Mayúscula (V/J/E/G/B/P) seguida de guion y números.')

def validar_telefono(value):
    # Validar teléfono venezolano: 0412/0414/0416/0422/0424/0426 + 7 dígitos
    if not re.match(r'^(0412|0414|0416|0422|0424|0426)[0-9]{7}$', value):
        raise ValidationError('Teléfono debe comenzar con 0412, 0414, 0416, 0422, 0424 o 0426 y tener 11 dígitos.')

class Cliente(models.Model):
    id_cliente = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    razon_social = models.CharField(max_length=255)
    nombre_comercial = models.CharField(max_length=255, null=True, blank=True)
    rif = models.CharField(max_length=20, unique=True, validators=[validar_rif])
    direccion = models.TextField(null=True, blank=True)
    telefono = models.CharField(max_length=50, null=True, blank=True, validators=[validar_telefono])
    email = models.EmailField(null=True, blank=True)
    contacto = models.CharField(max_length=100, null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.razon_social


class ContactoCliente(models.Model):
    id_contacto = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='contactos_cliente')
    id_cliente = models.ForeignKey('Cliente', on_delete=models.CASCADE, related_name='contactos')
    nombre_contacto = models.CharField(max_length=100)
    apellido_contacto = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100, null=True, blank=True)
    telefono_directo = models.CharField(max_length=50, null=True, blank=True)
    telefono_movil = models.CharField(max_length=50, null=True, blank=True)
    email_contacto = models.EmailField()
    fecha_nacimiento = models.DateField(null=True, blank=True)
    es_contacto_principal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_contacto_cliente'
        verbose_name = 'Contacto de Cliente'
        verbose_name_plural = 'Contactos de Cliente'

    def __str__(self):
        return f"{self.nombre_contacto} {self.apellido_contacto} - {self.id_cliente.razon_social}"


class DireccionCliente(models.Model):
    TIPOS_DIRECCION = [
        ('FISCAL', 'Fiscal'),
        ('COMERCIAL', 'Comercial'),
        ('ENTREGA', 'Entrega'),
        ('FACTURACION', 'Facturación'),
        ('OTRA', 'Otra'),
    ]

    id_direccion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='direcciones_cliente')
    id_cliente = models.ForeignKey('Cliente', on_delete=models.CASCADE, related_name='direcciones')
    tipo_direccion = models.CharField(max_length=20, choices=TIPOS_DIRECCION)
    direccion_completa = models.TextField()
    ciudad = models.CharField(max_length=100)
    estado_provincia = models.CharField(max_length=100)
    codigo_postal = models.CharField(max_length=20, null=True, blank=True)
    pais = models.CharField(max_length=100, default='Venezuela')
    telefono = models.CharField(max_length=50, null=True, blank=True)
    persona_contacto = models.CharField(max_length=100, null=True, blank=True)
    es_direccion_principal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_direccion_cliente'
        verbose_name = 'Dirección de Cliente'
        verbose_name_plural = 'Direcciones de Cliente'

    def __str__(self):
        return f"{self.tipo_direccion} - {self.id_cliente.razon_social} ({self.ciudad})"
