import re
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.base_models import IntegrationFieldsMixin, OmniBaseModel


def validar_rif(value):
    if not re.match(r"^[VJEGBP]-[0-9]+$", value):
        raise ValidationError("RIF debe tener formato Letra-Mayúscula (V/J/E/G/B/P) seguida de guion y números.")


def validar_telefono(value):
    # Acepta móviles y fijos venezolanos, y formatos internacionales con +
    cleaned = re.sub(r"[\s\-\(\)]", "", value)
    if not re.match(r"^\+?[0-9]{7,15}$", cleaned):
        raise ValidationError("Teléfono inválido. Ingrese entre 7 y 15 dígitos, con prefijo + opcional.")


class Cliente(OmniBaseModel, IntegrationFieldsMixin):
    """
    Cliente del negocio. Hereda timestamps, soft-delete e integración externa.
    RIF único por empresa (no globalmente) para soportar multi-tenant.
    """

    id_cliente = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="clientes")
    razon_social = models.CharField(max_length=255)
    nombre_comercial = models.CharField(max_length=255, null=True, blank=True)
    rif = models.CharField(max_length=20, validators=[validar_rif])
    direccion = models.TextField(null=True, blank=True)
    telefono = models.CharField(max_length=50, null=True, blank=True, validators=[validar_telefono])
    email = models.EmailField(null=True, blank=True)
    contacto = models.CharField(max_length=100, null=True, blank=True)
    tipo_cliente = models.CharField(
        max_length=10,
        choices=[("CONTADO", "Contado"), ("CREDITO", "Crédito")],
        default="CONTADO",
    )
    limite_credito = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Límite de crédito aprobado. 0 = sin límite definido (requiere tipo_cliente=CREDITO).",
    )
    dias_credito = models.PositiveSmallIntegerField(
        default=0,
        help_text="Días de plazo de crédito.",
    )

    class Meta:
        ordering = ["razon_social"]
        unique_together = [["id_empresa", "rif"]]

    def __str__(self):
        return self.razon_social


class ContactoCliente(OmniBaseModel):
    id_contacto = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="contactos_cliente")
    id_cliente = models.ForeignKey("Cliente", on_delete=models.CASCADE, related_name="contactos")
    nombre_contacto = models.CharField(max_length=100)
    apellido_contacto = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100, null=True, blank=True)
    telefono_directo = models.CharField(max_length=50, null=True, blank=True)
    telefono_movil = models.CharField(max_length=50, null=True, blank=True)
    email_contacto = models.EmailField()
    fecha_nacimiento = models.DateField(null=True, blank=True)
    es_contacto_principal = models.BooleanField(default=False)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "crm_contacto_cliente"
        verbose_name = "Contacto de Cliente"
        verbose_name_plural = "Contactos de Cliente"

    def __str__(self):
        return f"{self.nombre_contacto} {self.apellido_contacto} - {self.id_cliente.razon_social}"


class DireccionCliente(OmniBaseModel):
    TIPOS_DIRECCION = [
        ("FISCAL", "Fiscal"),
        ("COMERCIAL", "Comercial"),
        ("ENTREGA", "Entrega"),
        ("FACTURACION", "Facturación"),
        ("OTRA", "Otra"),
    ]

    id_direccion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="direcciones_cliente")
    id_cliente = models.ForeignKey("Cliente", on_delete=models.CASCADE, related_name="direcciones")
    tipo_direccion = models.CharField(max_length=20, choices=TIPOS_DIRECCION)
    direccion_completa = models.TextField()
    ciudad = models.CharField(max_length=100)
    estado_provincia = models.CharField(max_length=100)
    codigo_postal = models.CharField(max_length=20, null=True, blank=True)
    pais = models.CharField(max_length=100, default="Venezuela")
    telefono = models.CharField(max_length=50, null=True, blank=True)
    persona_contacto = models.CharField(max_length=100, null=True, blank=True)
    es_direccion_principal = models.BooleanField(default=False)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "crm_direccion_cliente"
        verbose_name = "Dirección de Cliente"
        verbose_name_plural = "Direcciones de Cliente"

    def __str__(self):
        return f"{self.tipo_direccion} - {self.id_cliente.razon_social} ({self.ciudad})"
